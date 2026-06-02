const express = require('express');
const bodyParser = require('body-parser');
const rateLimitMw = require('express-rate-limit');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const app = express();
const PORT = process.env.PORT || 8080;

// ============================================================================
// v2.x Tick Backend (FastAPI) 代理配置
// ============================================================================
// 通过 TICK_BACKEND_URL 环境变量覆盖默认 (http://127.0.0.1:8000)
// 若后端不可达,/api/tick/* 路由返回 503;/create-novel 和 /continue-novel
// 仍然 fallback 到旧的 spawn Python 行为
// ============================================================================
const TICK_BACKEND_URL = (process.env.TICK_BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const TICK_HEALTH_CACHE_MS = 5000;
let _tickBackendHealthy = null;
let _tickBackendCheckedAt = 0;

// ============================================================================
// 速率限制中间件（CodeQL 识别 express-rate-limit）
// ============================================================================
// 写操作（POST/PUT/DELETE）：每分钟 30 次，每 IP
const writeLimiter = rateLimitMw({
    windowMs: 60 * 1000,
    max: 30,
    standardHeaders: true,
    legacyHeaders: false,
    message: { success: false, message: '请求过于频繁，请稍后重试' },
});
// 昂贵读操作（章节内容、记忆数据）：每分钟 120 次
const readLimiter = rateLimitMw({
    windowMs: 60 * 1000,
    max: 120,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: '请求过于频繁，请稍后重试' },
});
// 任务触发（生成/继续/停止）：每分钟 5 次（与已有自定义 rateLimit 一致）
const taskLimiter = rateLimitMw({
    windowMs: 60 * 1000,
    max: 5,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: '生成任务触发过于频繁，请稍后重试' },
});

// 使用虚拟环境的 Python 解释器
const PYTHON_PATH = (() => {
    const venvPython = path.join(__dirname, '..', '.venv', process.platform === 'win32' ? 'Scripts' : 'bin', 'python');
    if (fs.existsSync(venvPython) || fs.existsSync(venvPython + '.exe')) {
        return venvPython;
    }
    return 'python';
})();

// 设置视图引擎
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// 安全头
app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    next();
});

// 中间件
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json({ limit: '100kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// 全局限速：所有写方法默认走 writeLimiter，所有 GET 走 readLimiter
// 单条路由可自行覆盖 (e.g. /create-novel 用更严格的 taskLimiter)
app.use((req, res, next) => {
    if (req.method === 'GET' || req.method === 'HEAD') {
        return readLimiter(req, res, next);
    }
    return writeLimiter(req, res, next);
});

// 简易速率限制（内存计数器）
const rateLimits = new Map();
function rateLimit(key, maxPerMinute) {
    const now = Date.now();
    const windowMs = 60000;
    const entry = rateLimits.get(key) || { count: 0, resetAt: now + windowMs };

    if (now > entry.resetAt) {
        entry.count = 0;
        entry.resetAt = now + windowMs;
    }

    entry.count++;
    rateLimits.set(key, entry);
    return entry.count > maxPerMinute;
}

// 进程管理：使用 Map 替代单一全局变量（修复竞态条件）
const runningProcesses = new Map();
let processIdCounter = 0;
let currentTopic = '';

// ============================================================================
// 工具函数
// ============================================================================

/**
 * 清理用户输入路径，只保留安全字符
 */
function sanitizePath(userInput) {
    if (!userInput || typeof userInput !== 'string') {
        return '';
    }
    return userInput.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '');
}

/**
 * 验证文件名是否安全
 */
function isValidFilename(filename) {
    if (!filename || typeof filename !== 'string') {
        return false;
    }
    // \u957f\u5ea6\u4e0a\u754c\u9632\u5fa1 ReDoS\uff1b\u6269\u5c55\u540d\u4f5c\u4e3a\u663e\u5f0f\u53ef\u9009 group \u907f\u514d\u6b67\u4e49\u91cf\u8bcd
    if (filename.length > 200) {
        return false;
    }
    return /^[a-zA-Z0-9\u4e00-\u9fa5_-]+(?:\.[a-zA-Z0-9]+)?$/.test(filename);
}

/**
 * 清理写入 .env 的值，去除换行符等危险字符
 */
function sanitizeEnvValue(value) {
    if (!value || typeof value !== 'string') return '';
    return value.replace(/[\r\n]/g, '').trim();
}

/**
 * 获取可用主题
 */
function getAvailableTopics() {
    const resultsDir = path.join(__dirname, '..', 'results');
    if (!fs.existsSync(resultsDir)) {
        return [];
    }
    return fs.readdirSync(resultsDir).filter(item => {
        const itemPath = path.join(resultsDir, item);
        return fs.statSync(itemPath).isDirectory();
    });
}

/**
 * 安全地读取 JSON 文件（仅允许 results/ 目录下的文件）
 */
function readJsonFile(filePath) {
    const resultsDir = path.resolve(path.join(__dirname, '..', 'results'));
    const resolvedPath = path.resolve(filePath);

    if (!resolvedPath.startsWith(resultsDir)) {
        return null;
    }

    if (!fs.existsSync(filePath)) {
        return null;
    }

    try {
        const content = fs.readFileSync(filePath, 'utf8');
        return JSON.parse(content);
    } catch (e) {
        return null;
    }
}

/**
 * 检查是否有正在运行的进程
 */
function hasRunningProcess() {
    return runningProcesses.size > 0;
}

// ============================================================================
// Tick Backend HTTP 代理工具
// ============================================================================

/**
 * 透传 HTTP 请求到 tick 后端,返回 {status, body(string)}。
 * 失败时 status=0, body=错误描述。
 */
function proxyToTickBackend(req, pathOverride) {
    return new Promise((resolve) => {
        const targetUrl = new URL((pathOverride || req.originalUrl), TICK_BACKEND_URL);
        const bodyText = req.method === 'GET' || req.method === 'HEAD'
            ? null
            : JSON.stringify(req.body || {});
        const headers = {
            'Accept': 'application/json',
        };
        if (bodyText) {
            headers['Content-Type'] = 'application/json';
            headers['Content-Length'] = Buffer.byteLength(bodyText);
        }

        const upstream = http.request({
            method: req.method,
            host: targetUrl.hostname,
            port: targetUrl.port || 80,
            path: targetUrl.pathname + targetUrl.search,
            headers,
            timeout: 30000,
        }, (resp) => {
            let chunks = [];
            resp.on('data', (c) => chunks.push(c));
            resp.on('end', () => {
                resolve({
                    status: resp.statusCode || 502,
                    body: Buffer.concat(chunks).toString('utf8'),
                    contentType: resp.headers['content-type'] || 'application/json',
                });
            });
        });

        upstream.on('error', (err) => {
            resolve({ status: 0, body: JSON.stringify({ error: String(err.message || err) }) });
        });
        upstream.on('timeout', () => {
            upstream.destroy();
            resolve({ status: 504, body: JSON.stringify({ error: 'tick backend timeout' }) });
        });

        if (bodyText) upstream.write(bodyText);
        upstream.end();
    });
}

async function tickBackendHealthy() {
    const now = Date.now();
    if (_tickBackendHealthy !== null && (now - _tickBackendCheckedAt) < TICK_HEALTH_CACHE_MS) {
        return _tickBackendHealthy;
    }
    const result = await proxyToTickBackend({ method: 'GET', originalUrl: '/' });
    _tickBackendHealthy = result.status >= 200 && result.status < 500;
    _tickBackendCheckedAt = now;
    return _tickBackendHealthy;
}

// 通用代理 - /api/tick/* 全部透传
app.all('/api/tick/*', async (req, res) => {
    const result = await proxyToTickBackend(req);
    if (result.status === 0) {
        return res.status(503).json({
            success: false,
            error: 'tick_backend_unreachable',
            backend_url: TICK_BACKEND_URL,
            detail: result.body,
        });
    }
    res.status(result.status);
    res.setHeader('Content-Type', result.contentType || 'application/json');
    res.send(result.body);
});

// ============================================================================
// 页面路由
// ============================================================================

app.get('/', (req, res) => {
    res.render('index', {
        topics: getAvailableTopics(),
        currentTopic: currentTopic,
        status: 'ready'
    });
});

app.get('/tick', (req, res) => {
    res.render('tick', {
        backendUrl: TICK_BACKEND_URL,
    });
});

// ============================================================================
// API Key 检查
// ============================================================================

app.get('/api/check-apikey', (req, res) => {
    const envPath = path.join(__dirname, '..', '.env');
    if (!fs.existsSync(envPath)) {
        return res.json({ configured: false });
    }
    const content = fs.readFileSync(envPath, 'utf8');
    const env = {};
    content.split('\n').forEach(line => {
        line = line.trim();
        if (line && !line.startsWith('#') && line.includes('=')) {
            const [k, ...v] = line.split('=');
            env[k.trim()] = v.join('=').trim();
        }
    });

    const provider = (env.LLM_PROVIDER || 'deepseek').toLowerCase();
    const keyByProvider = {
        deepseek: env.DEEPSEEK_API_KEY || '',
        mimo: env.MIMO_API_KEY || '',
        custom: env.CUSTOM_API_KEY || '',
    };
    const activeKey = keyByProvider[provider] || '';

    // DeepSeek 要求 sk- 前缀，其他提供商只要求非空
    const configured = provider === 'deepseek'
        ? (activeKey.length >= 20 && activeKey.startsWith('sk-'))
        : activeKey.length > 0;

    res.json({ configured, provider });
});

// ============================================================================
// 配置 API（不返回明文密钥）
// ============================================================================

const SECRET_KEYS = new Set([
    'DEEPSEEK_API_KEY',
    'DASHSCOPE_API_KEY',
    'MIMO_API_KEY',
    'CUSTOM_API_KEY',
]);

// 已知 LLM 提供商（与 core/config.py 保持一致）
const LLM_PROVIDERS = ['deepseek', 'mimo', 'custom'];

app.get('/api/config', (req, res) => {
    const envPath = path.join(__dirname, '..', '.env');
    const config = {};

    if (fs.existsSync(envPath)) {
        const content = fs.readFileSync(envPath, 'utf8');
        const lines = content.split('\n');

        lines.forEach(line => {
            line = line.trim();
            if (line && !line.startsWith('#') && line.includes('=')) {
                const [key, ...valueParts] = line.split('=');
                const k = key.trim();
                const value = valueParts.join('=').trim();

                // 密钥类字段只返回是否已配置和掩码
                if (SECRET_KEYS.has(k)) {
                    config[k] = value ? ('****' + value.slice(-4)) : '';
                    config[k + '_CONFIGURED'] = value.length >= 20;
                } else {
                    config[k] = value;
                }
            }
        });
    }

    res.json({ success: true, config });
});

// 读取 .env，返回原始 key→value 字典（明文）
function readEnv(envPath) {
    const existing = {};
    if (fs.existsSync(envPath)) {
        const content = fs.readFileSync(envPath, 'utf8');
        content.split('\n').forEach(line => {
            line = line.trim();
            if (line && !line.startsWith('#') && line.includes('=')) {
                const [key, ...valueParts] = line.split('=');
                existing[key.trim()] = valueParts.join('=').trim();
            }
        });
    }
    return existing;
}

// 解析前端传来的密钥：若是 **** 掩码则保留原值
function resolveSecret(newValue, existingValue) {
    if (!newValue) return existingValue || '';
    if (typeof newValue === 'string' && newValue.startsWith('****')) {
        return existingValue || '';
    }
    return newValue;
}

app.post('/api/config', writeLimiter, (req, res) => {
    const newConfig = req.body;
    const envPath = path.join(__dirname, '..', '.env');
    const existing = readEnv(envPath);
    const errors = [];

    // --- 提供商选择 -------------------------------------------------------
    let provider = (newConfig.LLM_PROVIDER || existing.LLM_PROVIDER || 'deepseek').toLowerCase();
    if (!LLM_PROVIDERS.includes(provider)) {
        errors.push(`未知 LLM 提供商: ${provider}（可选 ${LLM_PROVIDERS.join(' / ')})`);
        provider = 'deepseek';
    }

    // --- 密钥处理 ---------------------------------------------------------
    const deepseekKey = resolveSecret(newConfig.DEEPSEEK_API_KEY, existing.DEEPSEEK_API_KEY);
    const mimoKey = resolveSecret(newConfig.MIMO_API_KEY, existing.MIMO_API_KEY);
    const customKey = resolveSecret(newConfig.CUSTOM_API_KEY, existing.CUSTOM_API_KEY);
    const dashscopeKey = resolveSecret(newConfig.DASHSCOPE_API_KEY, existing.DASHSCOPE_API_KEY);

    // DeepSeek 密钥仅做轻量格式校验（其他提供商无统一格式）
    if (provider === 'deepseek' && deepseekKey) {
        if (!deepseekKey.startsWith('sk-')) {
            errors.push('DeepSeek API 密钥格式错误，应以 sk- 开头');
        } else if (deepseekKey.length < 20) {
            errors.push('DeepSeek API 密钥长度不足');
        }
    }

    // active 提供商必须有 key
    const activeKey = { deepseek: deepseekKey, mimo: mimoKey, custom: customKey }[provider];
    if (!activeKey) {
        errors.push(`当前选择的提供商 [${provider}] 缺少 API Key`);
    }
    if (provider === 'custom' && !(newConfig.CUSTOM_BASE_URL || existing.CUSTOM_BASE_URL)) {
        errors.push('自定义提供商必须填写 CUSTOM_BASE_URL');
    }

    // --- 通用参数 ---------------------------------------------------------
    const maxTokens = parseInt(newConfig.LLM_MAX_TOKENS || newConfig.DEEPSEEK_MAX_TOKENS || existing.LLM_MAX_TOKENS || existing.DEEPSEEK_MAX_TOKENS || '8192');
    if (isNaN(maxTokens) || maxTokens < 100 || maxTokens > 32768) {
        errors.push('Max Tokens 必须在 100-32768 之间');
    }

    const temperatureRaw = newConfig.LLM_TEMPERATURE || newConfig.DEEPSEEK_TEMPERATURE || existing.LLM_TEMPERATURE || existing.DEEPSEEK_TEMPERATURE || '0.7';
    const temperature = parseFloat(temperatureRaw);
    if (isNaN(temperature) || temperature < 0 || temperature > 1) {
        errors.push('Temperature 必须在 0-1 之间');
    }

    const imagesPerChapter = parseInt(newConfig.DASHSCOPE_IMAGES_PER_CHAPTER);
    if (!isNaN(imagesPerChapter) && (imagesPerChapter < 1 || imagesPerChapter > 4)) {
        errors.push('每章图片数必须在 1-4 之间');
    }

    if (errors.length > 0) {
        return res.status(400).json({ success: false, errors });
    }

    // --- 写回 .env --------------------------------------------------------
    const pick = (k, fallback = '') =>
        sanitizeEnvValue(newConfig[k] || existing[k] || fallback);

    let content = '# 无限小说生成系统 - 环境变量配置\n';
    content += '# 自动生成，请勿删除\n\n';

    content += '# LLM 提供商：deepseek | mimo | custom\n';
    content += `LLM_PROVIDER=${sanitizeEnvValue(provider)}\n`;
    content += `LLM_MAX_TOKENS=${sanitizeEnvValue(String(maxTokens))}\n`;
    content += `LLM_TEMPERATURE=${sanitizeEnvValue(String(temperature))}\n`;
    content += `LLM_TIMEOUT=${pick('LLM_TIMEOUT', '120')}\n\n`;

    content += '# DeepSeek API 配置\n';
    content += `DEEPSEEK_API_KEY=${sanitizeEnvValue(deepseekKey)}\n`;
    content += `DEEPSEEK_BASE_URL=${pick('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')}\n`;
    content += `DEEPSEEK_MODEL=${pick('DEEPSEEK_MODEL', 'deepseek-chat')}\n\n`;

    content += '# MiMo (小米) API 配置\n';
    content += `MIMO_API_KEY=${sanitizeEnvValue(mimoKey)}\n`;
    content += `MIMO_BASE_URL=${pick('MIMO_BASE_URL', 'https://token-plan-cn.xiaomimimo.com/v1')}\n`;
    content += `MIMO_MODEL=${pick('MIMO_MODEL', 'mimo-chat')}\n\n`;

    content += '# 自定义 OpenAI 兼容端点\n';
    content += `CUSTOM_API_KEY=${sanitizeEnvValue(customKey)}\n`;
    content += `CUSTOM_BASE_URL=${pick('CUSTOM_BASE_URL')}\n`;
    content += `CUSTOM_MODEL=${pick('CUSTOM_MODEL')}\n\n`;

    content += '# DashScope API 配置（图片生成）\n';
    content += `DASHSCOPE_API_KEY=${sanitizeEnvValue(dashscopeKey)}\n`;
    content += `DASHSCOPE_BASE_URL=${pick('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/api/v1')}\n`;
    content += `DASHSCOPE_MODEL=${pick('DASHSCOPE_MODEL', 'qwen-image-2.0')}\n`;
    content += `DASHSCOPE_IMAGES_PER_CHAPTER=${pick('DASHSCOPE_IMAGES_PER_CHAPTER', '2')}\n`;
    content += `DASHSCOPE_WATERMARK=${pick('DASHSCOPE_WATERMARK', 'true')}\n\n`;

    content += '# 多媒体配置\n';
    content += `ENABLE_MULTIMEDIA=${pick('ENABLE_MULTIMEDIA', 'false')}\n`;
    content += `TTS_VOICE=${pick('TTS_VOICE', 'zh-CN-XiaoxiaoNeural')}\n`;
    content += `TTS_RATE=${pick('TTS_RATE', '+0%')}\n`;
    content += `TTS_VOLUME=${pick('TTS_VOLUME', '+0%')}\n\n`;

    content += '# 前端配置\n';
    content += `FRONTEND_PORT=${pick('FRONTEND_PORT', '8080')}\n`;
    content += `FRONTEND_HOST=${pick('FRONTEND_HOST', '127.0.0.1')}\n\n`;

    try {
        fs.writeFileSync(envPath, content, 'utf8');
        res.json({ success: true, message: '配置已保存', provider });
    } catch (error) {
        res.status(500).json({ success: false, message: '保存配置失败' });
    }
});

// 返回受支持的提供商元数据（前端 UI 用）
app.get('/api/config/providers', (req, res) => {
    res.json({
        success: true,
        providers: [
            { id: 'deepseek', label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
            { id: 'mimo', label: 'MiMo (小米)', base_url: 'https://token-plan-cn.xiaomimimo.com/v1', model: 'mimo-chat' },
            { id: 'custom', label: '自定义', base_url: '', model: '' },
        ],
    });
});

// ============================================================================
// 小说项目管理 API (与 core/novel_manager.py 共享 results/manifest.json)
// ============================================================================

const RESULTS_DIR = path.resolve(path.join(__dirname, '..', 'results'));
const MANIFEST_PATH = path.join(RESULTS_DIR, 'manifest.json');
const LEGACY_SKIP = new Set(['__pycache__']);

function ensureResultsDir() {
    if (!fs.existsSync(RESULTS_DIR)) {
        fs.mkdirSync(RESULTS_DIR, { recursive: true });
    }
}

function loadManifest() {
    if (!fs.existsSync(MANIFEST_PATH)) return [];
    try {
        const data = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
        return Array.isArray(data) ? data : [];
    } catch {
        return [];
    }
}

function saveManifest(entries) {
    ensureResultsDir();
    fs.writeFileSync(MANIFEST_PATH, JSON.stringify(entries, null, 2) + '\n', 'utf8');
}

function nowIso() {
    return new Date().toISOString();
}

function slugify(title) {
    // 与 Python 版保持一致：保留中文/字母/数字/下划线/短横，其他换 _
    // 长度上界优先于正则替换，避免极长输入触发 ReDoS
    const bounded = String(title).slice(0, 100);
    const cleaned = bounded.replace(/[^\w一-鿿-]/g, '_').slice(0, 30);
    // 用 for 循环手动 trim 下划线，避免使用易被 CodeQL 误报的歧义正则
    let start = 0;
    let end = cleaned.length;
    while (start < end && cleaned.charCodeAt(start) === 95) start++;
    while (end > start && cleaned.charCodeAt(end - 1) === 95) end--;
    const trimmed = cleaned.slice(start, end);
    const suffix = (Date.now() % 0xFFFFFF).toString(16);
    return trimmed ? `${trimmed}_${suffix}` : suffix;
}

function scanLegacyTopics() {
    ensureResultsDir();
    return fs.readdirSync(RESULTS_DIR)
        .filter(name => {
            if (LEGACY_SKIP.has(name) || name.startsWith('.')) return false;
            try {
                return fs.statSync(path.join(RESULTS_DIR, name)).isDirectory();
            } catch {
                return false;
            }
        });
}

function backfillLegacy(entries) {
    const known = new Set(entries.map(e => e.id));
    let changed = false;
    for (const topic of scanLegacyTopics()) {
        if (known.has(topic)) continue;
        let ts = nowIso();
        try {
            ts = fs.statSync(path.join(RESULTS_DIR, topic)).mtime.toISOString();
        } catch {}
        entries.push({ id: topic, title: topic, created_at: ts, updated_at: ts });
        changed = true;
    }
    if (changed) saveManifest(entries);
    return entries;
}

function listNovels() {
    let entries = backfillLegacy(loadManifest());
    return [...entries].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
}

// --- REST endpoints --------------------------------------------------------

app.get('/api/novels', (req, res) => {
    try {
        res.json({ success: true, novels: listNovels() });
    } catch (e) {
        res.status(500).json({ success: false, message: '读取小说列表失败' });
    }
});

app.post('/api/novels', writeLimiter, (req, res) => {
    const title = (req.body && req.body.title) ? String(req.body.title).trim() : '未命名小说';
    if (!title) return res.status(400).json({ success: false, message: '标题不能为空' });

    const entries = loadManifest();
    let novelId = slugify(title);
    while (entries.some(e => e.id === novelId)) {
        novelId = `${novelId}_${(Date.now() % 0xFFFFFF).toString(16)}`;
    }
    const novelDir = path.join(RESULTS_DIR, novelId);
    if (!fs.existsSync(novelDir)) fs.mkdirSync(novelDir, { recursive: true });

    const now = nowIso();
    const entry = { id: novelId, title, created_at: now, updated_at: now };
    entries.push(entry);
    saveManifest(entries);
    res.json({ success: true, novel: entry });
});

app.put('/api/novels/:id', writeLimiter, (req, res) => {
    const novelId = sanitizePath(req.params.id);
    const newTitle = (req.body && req.body.title) ? String(req.body.title).trim() : '';
    if (!newTitle) return res.status(400).json({ success: false, message: '标题不能为空' });

    const entries = loadManifest();
    const entry = entries.find(e => e.id === novelId);
    if (!entry) return res.status(404).json({ success: false, message: '小说不存在' });

    entry.title = newTitle;
    entry.updated_at = nowIso();
    saveManifest(entries);
    res.json({ success: true, novel: entry });
});

app.delete('/api/novels/:id', writeLimiter, (req, res) => {
    const novelId = sanitizePath(req.params.id);
    const entries = loadManifest();
    const idx = entries.findIndex(e => e.id === novelId);
    if (idx === -1) return res.status(404).json({ success: false, message: '小说不存在' });

    entries.splice(idx, 1);
    saveManifest(entries);

    const novelDir = path.join(RESULTS_DIR, novelId);
    if (path.resolve(novelDir).startsWith(RESULTS_DIR) && fs.existsSync(novelDir)) {
        fs.rmSync(novelDir, { recursive: true, force: true });
    }
    res.json({ success: true });
});

// ============================================================================
// 主题和章节 API
// ============================================================================

app.get('/chapters', (req, res) => {
    try {
        res.json(getAvailableTopics());
    } catch (error) {
        res.status(500).json({ error: '获取主题列表失败' });
    }
});

app.get('/chapters/:topic', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const topicDir = path.join(__dirname, '..', 'results', sanitizedTopic);
    const resultsDir = path.resolve(path.join(__dirname, '..', 'results'));

    if (!path.resolve(topicDir).startsWith(resultsDir)) {
        return res.status(403).json({ error: '非法的访问路径' });
    }

    if (!fs.existsSync(topicDir)) {
        return res.json([]);
    }

    const files = fs.readdirSync(topicDir)
        .filter(file => file.startsWith('chapter_') && file.endsWith('.txt'))
        .sort();

    const chapters = files.map((file, index) => {
        const content = fs.readFileSync(path.join(topicDir, file), 'utf8');
        const lines = content.split('\n');
        let title = file.replace('chapter_', '').replace('.txt', '');
        if (lines[0] && lines[0].startsWith('#')) {
            title = lines[0].substring(2).trim();
        }
        const bodyLines = lines.slice(1).join('\n').trim();
        const preview = bodyLines.substring(0, 200) + (bodyLines.length > 200 ? '...' : '');

        return { filename: file, title, chapterNum: index + 1, preview };
    });

    res.json(chapters);
});

app.get('/chapter-content/:topic/:filename', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const { filename } = req.params;

    if (!isValidFilename(filename)) {
        return res.status(400).send('非法的文件名');
    }

    const filePath = path.join(__dirname, '..', 'results', sanitizedTopic, filename);
    const resultsDir = path.resolve(path.join(__dirname, '..', 'results'));

    if (!path.resolve(filePath).startsWith(resultsDir)) {
        return res.status(403).send('非法的访问路径');
    }

    if (!fs.existsSync(filePath)) {
        return res.status(404).send('章节不存在');
    }

    res.send(fs.readFileSync(filePath, 'utf8'));
});

// ============================================================================
// 记忆系统 API
// ============================================================================

app.get('/api/memory/relationships/:topic', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const data = readJsonFile(path.join(__dirname, '..', 'results', sanitizedTopic, 'character_relationships.json'));
    res.json({ success: true, relationships: data || {} });
});

app.get('/api/memory/entities/:topic', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const data = readJsonFile(path.join(__dirname, '..', 'results', sanitizedTopic, 'entity_state.json'));
    res.json({ success: true, entities: data || {} });
});

app.get('/api/memory/summary/:topic', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const data = readJsonFile(path.join(__dirname, '..', 'results', sanitizedTopic, 'hierarchical_summary.json'));
    res.json({ success: true, summary: data || {} });
});

app.get('/api/memory/events/:topic', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const data = readJsonFile(path.join(__dirname, '..', 'results', sanitizedTopic, 'long_term_events.json'));
    res.json({ success: true, events: data || [] });
});

app.get('/api/memory/chapter/:topic/:chapterNum', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const num = parseInt(req.params.chapterNum);

    if (isNaN(num) || num < 1) {
        return res.status(400).json({ error: '非法的章节号' });
    }

    const topicDir = path.join(__dirname, '..', 'results', sanitizedTopic);
    const relationships = readJsonFile(path.join(topicDir, 'character_relationships.json')) || {};
    const entityState = readJsonFile(path.join(topicDir, 'entity_state.json')) || {};
    const snapshotFile = path.join(topicDir, 'entity_snapshots', `chapter_${String(num).padStart(3, '0')}.json`);
    const snapshot = readJsonFile(snapshotFile);
    const allEvents = readJsonFile(path.join(topicDir, 'long_term_events.json')) || [];
    const chapterEvents = allEvents.filter(e => e.chapter_num === num);
    const summary = readJsonFile(path.join(topicDir, 'hierarchical_summary.json')) || {};
    const slidingWindow = readJsonFile(path.join(topicDir, 'sliding_window.json')) || {};

    res.json({
        success: true, chapterNum: num,
        relationships,
        entityState: snapshot || entityState,
        chapterEvents, allEvents, summary, slidingWindow
    });
});

// ============================================================================
// 小说生成 API（通过环境变量传参，不在代码字符串中拼接用户输入）
// ============================================================================

app.post('/create-novel', taskLimiter, async (req, res) => {
    const { topic } = req.body;

    if (!topic || !topic.trim()) {
        return res.status(400).json({ success: false, message: '主题不能为空' });
    }
    if (topic.length > 100) {
        return res.status(400).json({ success: false, message: '主题长度不能超过 100 个字符' });
    }
    if (rateLimit('create', 5)) {
        return res.status(429).json({ success: false, message: '请求过于频繁，请稍后再试' });
    }
    if (hasRunningProcess()) {
        return res.status(409).json({ success: false, message: '当前有正在运行的生成任务，请等待完成后再试' });
    }

    currentTopic = topic;

    // v2.x 优先路径: 检测 tick 后端;就绪则推进 1 个 tick 代替 spawn
    // 若未 bootstrap 或 tick 后端不可达,fallback 到 v1.x spawn
    if (process.env.FORCE_LEGACY_GENERATOR !== '1' && await tickBackendHealthy()) {
        const statusResult = await proxyToTickBackend({ method: 'GET', originalUrl: '/api/tick/status' });
        if (statusResult.status === 200) {
            try {
                const status = JSON.parse(statusResult.body);
                if (status.character_count > 0) {
                    // 直接推 1 个 tick 让 Orchestrator 产出第一章
                    const runResult = await proxyToTickBackend({
                        method: 'POST', originalUrl: '/api/tick/run', body: {},
                    });
                    return res.json({
                        success: runResult.status === 200,
                        message: runResult.status === 200
                            ? `tick 后端已生成新章节`
                            : `tick 后端推进失败`,
                        backend: 'tick',
                        result: runResult.body,
                        topics: getAvailableTopics(),
                    });
                }
                // 未 bootstrap - 提示用户先跑 bootstrap_prompts CLI
                console.log('[create-novel] tick backend not bootstrapped, falling back to v1.x spawn');
            } catch (e) {
                console.error('[create-novel] status parse failed:', e);
            }
        }
    }

    // v1.x fallback: spawn Python
    const processId = ++processIdCounter;

    const pythonProcess = spawn(PYTHON_PATH, [
        path.join(__dirname, '..', 'create_novel.py')
    ], {
        cwd: path.join(__dirname, '..'),
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            NOVEL_TOPIC: topic,
            LEGACY_GENERATOR: '1'  // 防 create_novel.py 自己再尝试 HTTP
        }
    });

    runningProcesses.set(processId, pythonProcess);

    let output = '';
    pythonProcess.stdout.on('data', (data) => { output += data.toString(); });
    pythonProcess.stderr.on('data', (data) => { output += data.toString(); });

    pythonProcess.on('close', (code) => {
        runningProcesses.delete(processId);
        res.json({
            success: code === 0,
            message: code === 0 ? `小说 "${topic}" 创建完成` : `小说 "${topic}" 生成失败或被中断`,
            output,
            topics: getAvailableTopics()
        });
    });

    pythonProcess.on('error', (err) => {
        runningProcesses.delete(processId);
        res.json({
            success: false,
            message: '启动生成进程失败',
            output: '启动 Python 进程失败',
            topics: getAvailableTopics()
        });
    });
});

app.post('/continue-novel', taskLimiter, async (req, res) => {
    const { topic, mode, customPrompt } = req.body;

    if (!topic) {
        return res.status(400).json({ success: false, message: '请选择要续写的小说主题' });
    }

    const sanitizedTopic = sanitizePath(topic);
    if (sanitizedTopic !== topic) {
        return res.status(400).json({ success: false, message: '主题包含非法字符' });
    }
    if (rateLimit('continue', 5)) {
        return res.status(429).json({ success: false, message: '请求过于频繁，请稍后再试' });
    }
    if (hasRunningProcess()) {
        return res.status(409).json({ success: false, message: '当前有正在运行的生成任务，请等待完成后再试' });
    }

    currentTopic = sanitizedTopic;

    // v2.x 优先路径: 检测 tick 后端
    if (process.env.FORCE_LEGACY_GENERATOR !== '1' && await tickBackendHealthy()) {
        const statusResult = await proxyToTickBackend({ method: 'GET', originalUrl: '/api/tick/status' });
        if (statusResult.status === 200) {
            try {
                const status = JSON.parse(statusResult.body);
                if (status.character_count > 0) {
                    // 若有 customPrompt 先注入事件
                    if (customPrompt && typeof customPrompt === 'string' && customPrompt.trim()) {
                        await proxyToTickBackend({
                            method: 'POST',
                            originalUrl: '/api/tick/inject-event',
                            body: {
                                description: customPrompt.trim().substring(0, 500),
                                narrative_value: 7,
                                visible_to: ['all'],
                                type: 'dramatic',
                            },
                        });
                    }
                    const runResult = await proxyToTickBackend({
                        method: 'POST', originalUrl: '/api/tick/run', body: {},
                    });
                    return res.json({
                        success: runResult.status === 200,
                        message: runResult.status === 200
                            ? `tick 后端已推进续写`
                            : `tick 后端推进失败`,
                        backend: 'tick',
                        result: runResult.body,
                        topics: getAvailableTopics(),
                    });
                }
            } catch (e) {
                console.error('[continue-novel] status parse failed:', e);
            }
        }
    }

    // v1.x fallback: spawn Python
    const processId = ++processIdCounter;

    const env = {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        NOVEL_TOPIC: sanitizedTopic,
        NOVEL_MODE: '1',
        LEGACY_GENERATOR: '1'  // 防 continue_novel.py 自己再尝试 HTTP
    };

    // 限制自定义提示词长度
    if (customPrompt && typeof customPrompt === 'string' && customPrompt.trim()) {
        env.NOVEL_CUSTOM_PROMPT = customPrompt.trim().substring(0, 2000);
    }

    // 不在 -c 字符串中插入用户输入，直接运行脚本文件
    const pythonProcess = spawn(PYTHON_PATH, [
        path.join(__dirname, '..', 'continue_novel.py')
    ], {
        cwd: path.join(__dirname, '..'),
        env: env
    });

    runningProcesses.set(processId, pythonProcess);

    let output = '';
    pythonProcess.stdout.on('data', (data) => { output += data.toString(); });
    pythonProcess.stderr.on('data', (data) => { output += data.toString(); });

    pythonProcess.on('close', (code) => {
        runningProcesses.delete(processId);
        res.json({
            success: code === 0,
            message: code === 0 ? `小说 "${sanitizedTopic}" 续写完成` : `小说 "${sanitizedTopic}" 续写失败或被中断`,
            output,
            topics: getAvailableTopics()
        });
    });

    pythonProcess.on('error', (err) => {
        runningProcesses.delete(processId);
        res.json({
            success: false,
            message: '启动生成进程失败',
            output: '启动 Python 进程失败',
            topics: getAvailableTopics()
        });
    });
});

// ============================================================================
// 多媒体 API
// ============================================================================

app.get('/multimedia/:topic/:chapterNum', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const sanitizedChapterNum = sanitizePath(req.params.chapterNum);

    if (!/^\d+$/.test(sanitizedChapterNum)) {
        return res.status(400).json({ error: '非法的章节号' });
    }

    const multimediaDir = path.join(__dirname, '..', 'results', sanitizedTopic, 'multimedia', `chapter_${sanitizedChapterNum}`);
    const resultsDir = path.resolve(path.join(__dirname, '..', 'results'));

    if (!path.resolve(multimediaDir).startsWith(resultsDir)) {
        return res.status(403).json({ error: '非法的访问路径' });
    }

    const multimediaResources = { audio: null, images: [], video: null };

    if (fs.existsSync(multimediaDir)) {
        const audioFiles = fs.readdirSync(multimediaDir).filter(f => f.endsWith('_audio.mp3'));
        if (audioFiles.length > 0) {
            multimediaResources.audio = `/multimedia-files/${sanitizedTopic}/chapter_${sanitizedChapterNum}/audio/${audioFiles[0]}`;
        }
        const imagesDir = path.join(multimediaDir, 'images');
        if (fs.existsSync(imagesDir)) {
            multimediaResources.images = fs.readdirSync(imagesDir)
                .filter(f => /\.(jpg|jpeg|png|gif)$/i.test(f))
                .map(img => `/multimedia-files/${sanitizedTopic}/chapter_${sanitizedChapterNum}/images/${img}`);
        }
        const videoDir = path.join(multimediaDir, 'video');
        if (fs.existsSync(videoDir)) {
            const videoFiles = fs.readdirSync(videoDir).filter(f => f.endsWith('_video.mp4'));
            if (videoFiles.length > 0) {
                multimediaResources.video = `/multimedia-files/${sanitizedTopic}/chapter_${sanitizedChapterNum}/video/${videoFiles[0]}`;
            }
        }
    }

    res.json(multimediaResources);
});

app.get('/multimedia-files/:topic/:chapterNum/:mediaType/:fileName', (req, res) => {
    const sanitizedTopic = sanitizePath(req.params.topic);
    const sanitizedChapterNum = sanitizePath(req.params.chapterNum);
    const sanitizedMediaType = sanitizePath(req.params.mediaType);
    const { fileName } = req.params;

    if (!['audio', 'images', 'video'].includes(sanitizedMediaType)) {
        return res.status(400).send('非法的媒体类型');
    }
    if (!isValidFilename(fileName)) {
        return res.status(400).send('非法的文件名');
    }

    const filePath = path.join(__dirname, '..', 'results', sanitizedTopic, 'multimedia', `chapter_${sanitizedChapterNum}`, sanitizedMediaType, fileName);
    const resultsDir = path.resolve(path.join(__dirname, '..', 'results'));

    if (!path.resolve(filePath).startsWith(resultsDir)) {
        return res.status(403).send('非法的访问路径');
    }

    if (fs.existsSync(filePath)) {
        res.sendFile(path.resolve(filePath));
    } else {
        res.status(404).send('文件不存在');
    }
});

// ============================================================================
// 进程管理
// ============================================================================

app.post('/stop-process', taskLimiter, (req, res) => {
    if (runningProcesses.size > 0) {
        for (const [id, proc] of runningProcesses) {
            proc.kill();
        }
        runningProcesses.clear();
        res.json({ success: true, message: '进程已停止' });
    } else {
        res.json({ success: false, message: '没有正在运行的进程' });
    }
});

// ============================================================================
// 启动服务器（默认绑定 127.0.0.1）
// ============================================================================

function startServer(port) {
    const host = '127.0.0.1';
    const server = app.listen(port, host, () => {
        console.log(`服务器运行在 http://localhost:${port}`);
    });

    server.on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
            console.log(`端口 ${port} 已被占用，尝试使用端口 ${port + 1}`);
            startServer(port + 1);
        } else {
            console.error('服务器启动错误:', err);
        }
    });
}

startServer(PORT);
