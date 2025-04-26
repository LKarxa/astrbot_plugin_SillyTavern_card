import os
import json
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
import astrbot.api.message_components as Comp

from .character_card_parser import parse_card
from .json_to_lorebook_yaml import json_to_lorebook_yaml

@register("strbot_plugin_SillyTavern_card", "LKarxa", "一个将酒馆PNG角色卡卡转换为Lorebook YAML和角色TXT的插件", "1.0.0", "https://github.com/LKarxa/astrbot_plugin_SillyTavern_card")
class CardConverterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 使用 StarTools.get_data_dir 获取插件数据目录
        plugin_data_dir = StarTools.get_data_dir("strbot_plugin_SillyTavern_card")
        self.data_dir = str(plugin_data_dir)
        
        # lorebook相关路径保持不变
        self.output_dir = os.path.join(os.getcwd(), "data", "lorebooks")
        
        self.char_dir = os.path.join(self.data_dir, "characters")
        
        # 创建card目录用于存放PNG文件
        self.card_dir = os.path.join(self.data_dir, "card")
        
        # 确保所有必要的目录都存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.char_dir, exist_ok=True)
        os.makedirs(self.card_dir, exist_ok=True)
        
        logger.info(f"插件数据目录: {self.data_dir}")
        logger.info(f"卡片目录已创建: {self.card_dir}")
        logger.info(f"角色目录已创建: {self.char_dir}")
        logger.info(f"输出目录已创建: {self.output_dir}")

    @filter.command("convert_card")
    async def convert_card(self, event: AstrMessageEvent, filename: str = ""):
        """将SillyTavern角色卡片PNG文件转换为Lorebook YAML和角色TXT"""
        # 如果没有提供文件名，列出可用的卡片文件
        if not filename:
            files = [f for f in os.listdir(self.card_dir) if f.lower().endswith('.png')]
            if not files:
                yield event.plain_result("错误: 卡片目录中没有找到PNG文件")
                yield event.plain_result(f"请将PNG文件放置在以下目录中: {self.card_dir}")
                return
            
            # 列出可用的卡片文件
            file_list = "\n".join(files)
            yield event.plain_result(f"请选择要转换的卡片文件，使用命令: /convert_card <文件名>\n\n可用的卡片文件:\n{file_list}")
            return
        
        # 构建完整的文件路径
        if os.path.isabs(filename):
            # 如果提供的是绝对路径，直接使用
            png_path = filename
        else:
            # 否则，在卡片目录中查找文件
            png_path = os.path.join(self.card_dir, filename)
            # 如果文件名没有.png后缀，自动添加
            if not png_path.lower().endswith('.png'):
                png_path += '.png'
        
        # 检查文件是否存在
        if not os.path.isfile(png_path):
            yield event.plain_result(f"错误: 找不到文件 {png_path}")
            return

        # 检查文件扩展名
        if not png_path.lower().endswith('.png'):
            yield event.plain_result("错误: 文件必须是PNG格式")
            return

        yield event.plain_result(f"开始处理PNG文件: {os.path.basename(png_path)}")

        try:
            # 1. 从PNG文件中提取JSON数据
            json_string = parse_card(png_path)
            if not json_string:
                yield event.plain_result("错误: 无法从PNG文件中提取角色数据")
                return

            # 2. 解析JSON数据
            try:
                json_data = json.loads(json_string)
            except json.JSONDecodeError as e:
                yield event.plain_result(f"错误: JSON解析失败 - {e}")
                return

            # 3. 处理JSON数据
            results: Optional[Tuple[str, str]] = await self._process_json_data(png_path, json_data, event) 
            if results:
                yaml_result, txt_content = results
                if txt_content:
                    # 直接发送提取的角色信息文本
                    yield event.plain_result(f"=== 角色卡信息 ===\n\n{txt_content}")
                else:
                    # 如果提取失败或内容为空
                    yield event.plain_result("未能提取有效的角色信息文本。")
                
                # 然后发送YAML处理结果
                yield event.plain_result(yaml_result)
            else:
                yield event.plain_result("处理失败，请检查日志")

        except Exception as e:
            logger.error(f"处理PNG文件时出错: {e}")
            yield event.plain_result(f"处理出错: {str(e)}")

    @filter.command("list_cards")
    async def list_cards(self, event: AstrMessageEvent):
        """列出可用的卡片文件"""
        files = [f for f in os.listdir(self.card_dir) if f.lower().endswith('.png')]
        if not files:
            yield event.plain_result("卡片目录中没有找到PNG文件")
            yield event.plain_result(f"请将PNG文件放置在以下目录中: {self.card_dir}")
            return
        
        # 列出可用的卡片文件
        file_list = "\n".join(files)
        yield event.plain_result(f"可用的卡片文件:\n{file_list}")
        yield event.plain_result(f"\n使用命令 /convert_card <文件名> 来转换卡片")

    async def _process_json_data(self, png_path: str, json_data: Dict[str, Any], event: AstrMessageEvent) -> Optional[Tuple[str, str]]:
        """处理JSON数据，转换为YAML并提取TXT内容字符串"""
        basename = os.path.basename(png_path)
        name = os.path.splitext(basename)[0]
        
        # 输出YAML文件路径
        output_yaml_path = os.path.join(self.output_dir, f"{name}.yaml")
        
        yaml_result = ""
        txt_content_result = ""
        
        # 1. 处理前半部分，提取角色信息为字符串
        txt_content_result = await self._extract_character_info(json_data)

        # 2. 处理后半部分，将整个JSON转换为YAML文件
        try:
            result_path = json_to_lorebook_yaml(json_data, output_yaml_path)
            
            if result_path and os.path.exists(result_path) and os.path.getsize(result_path) > 0:
                yaml_result = f"成功! YAML文件已保存到: {result_path}"
            else:
                logger.warning(f"JSON数据转YAML时出现问题，输出可能为空: {output_yaml_path}")
                yaml_result = f"警告: YAML文件可能未正确生成，请检查: {output_yaml_path}"
                
        except Exception as e:
            logger.error(f"转换JSON数据到YAML过程中出错: {e}")
            yaml_result = f"错误: 转换JSON数据到YAML失败 - {str(e)}"
        
        return yaml_result, txt_content_result

    async def _extract_character_info(self, json_data: Dict[str, Any]) -> str:
        """
        从JSON数据中提取角色信息并返回格式化后的字符串
        映射关系：
        - name → name
        - description → prompt
        - begin_dialogs/first_mes/greeting/... → first_mes
        所有输出值都用双引号包裹。
        """
        try:
            name = str(json_data.get('name', ''))
            description = str(json_data.get('description', ''))
            first_mes_raw = ""
            
            if 'first_mes' in json_data:
                first_mes_raw = json_data['first_mes']
            elif 'begin_dialogs' in json_data:
                begin_dialogs = json_data['begin_dialogs']
                if isinstance(begin_dialogs, list) and begin_dialogs:
                    first_mes_raw = begin_dialogs[0]
                elif isinstance(begin_dialogs, str):
                    first_mes_raw = begin_dialogs
            elif 'greeting' in json_data:
                first_mes_raw = json_data['greeting']
            elif 'example_dialog' in json_data and json_data['example_dialog']:
                example_dialog = json_data['example_dialog']
                if isinstance(example_dialog, list) and example_dialog:
                    first_mes_raw = example_dialog[0]
            elif 'char_greeting' in json_data:
                first_mes_raw = json_data['char_greeting']
            elif 'alternate_greetings' in json_data and json_data['alternate_greetings']:
                alternate_greetings = json_data['alternate_greetings']
                if isinstance(alternate_greetings, list) and alternate_greetings:
                    first_mes_raw = alternate_greetings[0]
            first_mes = str(first_mes_raw)

            def quote_value(value: str) -> str:
                escaped_value = value.replace('"', '\\"')
                escaped_value = escaped_value.replace('\n', '\\n').replace('\r', '') 
                return f'"{escaped_value}"'

            txt_content = f"name: {quote_value(name)}\n\n"
            txt_content += f"prompt: {quote_value(description)}\n\n"
            txt_content += f"first_mes: {quote_value(first_mes)}"
            
            return txt_content
            
        except Exception as e:
            logger.error(f"提取角色信息时出错: {e}")
            return ""

    @filter.command("help_convert")
    async def help_convert(self, event: AstrMessageEvent):
        """显示卡片转换插件的使用说明"""
        help_text = """
卡片转换插件使用帮助:

1. 命令格式:
   /convert_card [文件名] - 转换指定的角色卡片文件
   /list_cards - 列出可用的卡片文件
   /help_convert - 显示此帮助信息

2. 说明:
   - 请将角色卡片PNG文件放在插件目录的card文件夹中
   - 使用 /convert_card 不带参数时会列出可用的文件
   - 使用时只需提供文件名即可，不需要完整路径
   
3. 转换功能:
   - 从PNG文件中提取角色卡片数据
   - 将角色信息(name/description/begin_dialogs)保存为TX直接发给用户
   - 按"entries"关键词切分JSON，将后部分转换为Lorebook的YAML格式
   
4. 输出文件:
   - 转换后的YAML文件将保存在 data/lorebooks/ 目录下
   - 两个文件均与原PNG文件同名

字段映射关系:
   - name → name
   - description → prompt
   - begin_dialogs → first_mes

示例:
   /convert_card character.png
   或简写为:
   /convert_card character
"""
        yield event.plain_result(help_text)