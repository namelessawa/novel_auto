const express = require('express');
const bodyParser = require('body-parser');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 8080;

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
    return /^[a-zA-Z0-9\u4e00-\u9fa5_-]+\.?[a-zA-Z0-9]*$/.test(filename);
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
// 页面路由
// ============================================================================

app.get('/', (req, res) => {
    res.render('index', {
        topics: getAvailableTopics(),
        currentTopic: currentTopic,
        status: 'ready'
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
    const match = content.match(/DEEPSEEK_API_KEY=(.+)/);
    const key = match ? match[1].trim() : '';
    res.json({
        configured: key.length >= 20 && key.startsWith('sk-')
    });
});

// ============================================================================
// 配置 API（不返回明文密钥）
// ============================================================================

const SECRET_KEYS = new Set(['DEEPSEEK_API_KEY', 'DASHSCOPE_API_KEY']);

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

app.post('/api/config', (req, res) => {
    const newConfig = req.body;
    const envPath = path.join(__dirname, '..', '.env');

    const errors = [];

    // 读取现有配置以保留未修改的密钥
    const existingConfig = {};
    if (fs.existsSync(envPath)) {
        const content = fs.readFileSync(envPath, 'utf8');
        content.split('\n').forEach(line => {
            line = line.trim();
            if (line && !line.startsWith('#') && line.includes('=')) {
                const [key, ...valueParts] = line.split('=');
                existingConfig[key.trim()] = valueParts.join('=').trim();
            }
        });
    }

    // 处理 API 密钥：如果前端传来的是掩码（****开头），则保留原值
    let deepseekKey = newConfig.DEEPSEEK_API_KEY || '';
    if (deepseekKey.startsWith('****')) {
        deepseekKey = existingConfig.DEEPSEEK_API_KEY || '';
    }
    if (deepseekKey && deepseekKey.trim()) {
        if (!deepseekKey.startsWith('sk-')) {
            errors.push('DeepSeek API 密钥格式错误，应以 sk- 开头');
        } else if (deepseekKey.length < 20) {
            errors.push('DeepSeek API 密钥长度不足');
        }
    }

    let dashscopeKey = newConfig.DASHSCOPE_API_KEY || '';
    if (dashscopeKey.startsWith('****')) {
        dashscopeKey = existingConfig.DASHSCOPE_API_KEY || '';
    }

    const maxTokens = parseInt(newConfig.DEEPSEEK_MAX_TOKENS);
    if (isNaN(maxTokens) || maxTokens < 100 || maxTokens > 32768) {
        errors.push('Max Tokens 必须在 100-32768 之间');
    }

    const temperature = parseFloat(newConfig.DEEPSEEK_TEMPERATURE);
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

    // 构建 .env（所有值均清理换行符）
    let content = '# 无限小说生成系统 - 环境变量配置\n';
    content += '# 自动生成，请勿删除\n\n';
    content += '# DeepSeek API 配置\n';
    content += `DEEPSEEK_API_KEY=${sanitizeEnvValue(deepseekKey)}\n`;
    content += `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1\n`;
    content += `DEEPSEEK_MODEL=${sanitizeEnvValue(newConfig.DEEPSEEK_MODEL || 'deepseek-chat')}\n`;
    content += `DEEPSEEK_MAX_TOKENS=${sanitizeEnvValue(newConfig.DEEPSEEK_MAX_TOKENS || '8192')}\n`;
    content += `DEEPSEEK_TEMPERATURE=${sanitizeEnvValue(newConfig.DEEPSEEK_TEMPERATURE || '0.7')}\n`;
    content += `DEEPSEEK_TIMEOUT=${sanitizeEnvValue(newConfig.DEEPSEEK_TIMEOUT || '120')}\n\n`;
    content += '# DashScope API 配置（图片生成）\n';
    content += `DASHSCOPE_API_KEY=${sanitizeEnvValue(dashscopeKey)}\n`;
    content += `DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1\n`;
    content += `DASHSCOPE_MODEL=${sanitizeEnvValue(newConfig.DASHSCOPE_MODEL || 'qwen-image-2.0')}\n`;
    content += `DASHSCOPE_IMAGES_PER_CHAPTER=${sanitizeEnvValue(newConfig.DASHSCOPE_IMAGES_PER_CHAPTER || '2')}\n`;
    content += `DASHSCOPE_WATERMARK=${sanitizeEnvValue(newConfig.DASHSCOPE_WATERMARK || 'true')}\n\n`;
    content += '# 多媒体配置\n';
    content += `ENABLE_MULTIMEDIA=${sanitizeEnvValue(newConfig.ENABLE_MULTIMEDIA || 'false')}\n`;
    content += `TTS_VOICE=${sanitizeEnvValue(newConfig.TTS_VOICE || 'zh-CN-XiaoxiaoNeural')}\n`;
    content += `TTS_RATE=${sanitizeEnvValue(newConfig.TTS_RATE || '+0%')}\n`;
    content += `TTS_VOLUME=${sanitizeEnvValue(newConfig.TTS_VOLUME || '+0%')}\n\n`;
    content += '# 前端配置\n';
    content += `FRONTEND_PORT=${sanitizeEnvValue(newConfig.FRONTEND_PORT || '8080')}\n`;
    content += `FRONTEND_HOST=127.0.0.1\n\n`;

    try {
        fs.writeFileSync(envPath, content, 'utf8');
        res.json({ success: true, message: '配置已保存' });
    } catch (error) {
        res.status(500).json({ success: false, message: '保存配置失败' });
    }
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

app.post('/create-novel', (req, res) => {
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
    const processId = ++processIdCounter;

    const pythonProcess = spawn(PYTHON_PATH, [
        path.join(__dirname, '..', 'create_novel.py')
    ], {
        cwd: path.join(__dirname, '..'),
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            NOVEL_TOPIC: topic
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

app.post('/continue-novel', (req, res) => {
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
    const processId = ++processIdCounter;

    const env = {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        NOVEL_TOPIC: sanitizedTopic,
        NOVEL_MODE: '1'
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

app.post('/stop-process', (req, res) => {
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
