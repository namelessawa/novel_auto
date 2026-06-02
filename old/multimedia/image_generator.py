"""
图片生成服务模块
使用阿里云DashScope API生成与小说内容相关的图片
"""

import json
import os
from pathlib import Path
from typing import List, Optional
import dashscope
from dashscope import MultiModalConversation


class ImageGenerator:
    """
    图片生成服务类
    使用阿里云DashScope API生成图片
    """
    
    def __init__(self, api_key: str = None, model: str = "qwen-image-2.0"):
        """
        初始化图片生成服务
        
        Args:
            api_key: DashScope API密钥
            model: 使用的模型名称
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("请设置DASHSCOPE_API_KEY环境变量或在初始化时传入api_key参数")
        
        self.model = model
        dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
    
    def generate_images_from_text(self, text: str, output_dir: str, num_images: int = 2) -> List[str]:
        """
        根据文本内容生成图片
        
        Args:
            text: 描述图片内容的文本
            output_dir: 图片输出目录
            num_images: 生成图片数量
            
        Returns:
            List[str]: 生成的图片文件路径列表
        """
        try:
            # 创建输出目录
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # 构建消息内容
            prompt = f"根据以下小说内容生成插图: {text[:500]}"  # 限制文本长度
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"text": prompt}
                    ]
                }
            ]
            
            # 调用API生成图片
            response = MultiModalConversation.call(
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                result_format='message',
                stream=False,
                n=num_images,
                watermark=True,
                negative_prompt=""
            )
            
            # 解析响应并保存图片
            image_paths = []
            if 'output' in response and 'choices' in response['output']:
                for i, choice in enumerate(response['output']['choices']):
                    if 'message' in choice and 'content' in choice['message']:
                        content_list = choice['message']['content']
                        for content_item in content_list:
                            if content_item.get('type') == 'image' and 'data' in content_item:
                                # 保存图片数据
                                image_data = content_item['data']
                                image_path = os.path.join(output_dir, f"generated_image_{i+1}.png")
                                with open(image_path, 'wb') as f:
                                    f.write(image_data)
                                image_paths.append(image_path)
            
            print(f"成功生成 {len(image_paths)} 张图片: {image_paths}")
            return image_paths
            
        except Exception as e:
            print(f"图片生成失败: {str(e)}")
            return []
    
    def generate_chapter_images(self, chapter_content: str, output_dir: str, num_images: int = 2) -> List[str]:
        """
        为整章内容生成相关图片
        
        Args:
            chapter_content: 章节内容
            output_dir: 图片输出目录
            num_images: 生成图片数量
            
        Returns:
            List[str]: 生成的图片文件路径列表
        """
        # 提取关键描述信息
        key_elements = self._extract_key_elements(chapter_content)
        
        # 构建更具体的提示词
        detailed_prompt = self._build_detailed_prompt(key_elements)
        
        return self.generate_images_from_text(detailed_prompt, output_dir, num_images)
    
    def _extract_key_elements(self, text: str) -> dict:
        """
        从文本中提取关键元素（人物、场景、动作等）
        
        Args:
            text: 输入文本
            
        Returns:
            dict: 提取的关键元素
        """
        # 简单的关键词提取（在实际应用中可以使用NLP模型进行更精确的提取）
        import re
        
        # 提取可能的人物描述
        character_patterns = [
            r'([男女][主角老少美帅靓健壮]\w{0,3})',
            r'(\w{2,4}[先生女士小姐])',
            r'([A-Z][a-z]+\s*[A-Z][a-z]*)'  # 英文名字
        ]
        
        characters = []
        for pattern in character_patterns:
            matches = re.findall(pattern, text)
            characters.extend(matches)
        
        # 提取场景描述
        scene_patterns = [
            r'(在|位于|来到|站在)[\u4e00-\u9fff]{2,8}(地方|房间|街道|城市|山|海|森林)',
            r'([\u4e00-\u9fff]{2,6}(房|室|厅|屋|店|馆|楼|园|场|馆))'
        ]
        
        scenes = []
        for pattern in scene_patterns:
            matches = re.findall(pattern, text)
            scenes.extend([match[-1] if isinstance(match, tuple) else match for match in matches])
        
        # 提取动作描述
        action_patterns = [
            r'(跑|走|跳|飞|坐|站|躺|爬|打|杀|救|爱|恨|哭|笑|说|喊|叫|唱|舞|战|斗|学|习|工作|吃|喝|玩|乐)[\u4e00-\u9fff]{0,5}',
            r'([\u4e00-\u9fff]{1,3}(地|着|了|过|掉|起|来|去|回|上|下|前|后|里|外)[\u4e00-\u9fff]{0,5})'
        ]
        
        actions = []
        for pattern in action_patterns:
            matches = re.findall(pattern, text)
            actions.extend([match if isinstance(match, str) else match[0] for match in matches])
        
        return {
            'characters': list(set(characters))[:5],  # 最多5个角色
            'scenes': list(set(scenes))[:3],  # 最多3个场景
            'actions': list(set(actions))[:5]   # 最多5个动作
        }
    
    def _build_detailed_prompt(self, key_elements: dict) -> str:
        """
        根据关键元素构建详细的图片生成提示词
        
        Args:
            key_elements: 关键元素字典
            
        Returns:
            str: 详细的提示词
        """
        prompt_parts = ["生成一张高质量的插图，描绘："]
        
        if key_elements['characters']:
            prompt_parts.append(f"角色: {', '.join(key_elements['characters'])}")
        
        if key_elements['scenes']:
            prompt_parts.append(f"场景: {', '.join(key_elements['scenes'])}")
        
        if key_elements['actions']:
            prompt_parts.append(f"动作: {', '.join(key_elements['actions'])}")
        
        # 添加艺术风格提示
        prompt_parts.append("风格: 适合小说插图的精美画风，细节丰富，色彩和谐")
        
        return "。".join(prompt_parts)


# 示例使用
if __name__ == "__main__":
    # 需要设置API密钥
    # os.environ["DASHSCOPE_API_KEY"] = "your-api-key-here"
    
    # 创建图片生成器实例
    try:
        generator = ImageGenerator()
        
        # 示例文本
        sample_text = "李明走进了一座古老的城堡，城堡内部装饰华丽，墙上挂着许多油画。突然，他听到了一阵奇怪的声音。"
        
        # 生成图片
        image_paths = generator.generate_images_from_text(sample_text, "./temp_images", num_images=2)
        
        if image_paths:
            print(f"图片生成成功: {image_paths}")
        else:
            print("图片生成失败！")
    except ValueError as e:
        print(f"API密钥未设置: {e}")
        print("请设置DASHSCOPE_API_KEY环境变量或在初始化时传入api_key参数")