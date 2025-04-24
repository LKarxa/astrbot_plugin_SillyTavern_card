#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import yaml
import os
import re
import argparse
import sys
import traceback
from typing import Dict, Any, List, Optional, Union

# Import astrbot logger
from astrbot.api import logger

class LoreBookConverter:
    """
    SillyTavern 角色卡片 JSON 到 Lorebook YAML 格式的转换类
    提供更结构化和可靠的转换流程
    """
    
    def __init__(self):
        """初始化转换器"""
        self.yaml_data = {
            "world_state": {},
            "user_state": [],
            "trigger": []
        }
        self.entries_processed = 0

    def quote_value(self, value: Any) -> Any:
        """
        如果值是字符串，则为其添加双引号并转义内部引号和换行符。
        否则按原样返回。
        """
        if isinstance(value, str):
            # 将内部的双引号转义为 \\""
            escaped_value = value.replace('"', '\\"')
            # 将换行符转义为 \\n，移除 \\r
            escaped_value = escaped_value.replace('\n', '\\n').replace('\r', '') 
            return f'"{escaped_value}"'
        return value # Return non-strings as is
    
    def clean_content(self, content: Any) -> Any:
        """清理内容中的特殊字符，确保YAML格式正确"""
        if isinstance(content, str):
            # 替换可能导致YAML解析问题的字符
            return content.replace('\t', '  ')
        return content
    
    def convert_position(self, pos_value) -> str:
        """转换position值: 0 -> "sys_start", 1 -> "sys_end", "after_char" -> "sys_start" 等"""
        # 扩展映射以包含字符串值
        position_map = {
            0: "sys_start",
            1: "sys_end",
            "0": "sys_start",
            "1": "sys_end",
            "after_char": "sys_start",  # 将 after_char 映射到 sys_start
            "before_char": "sys_start", # 示例：添加其他可能的映射
            "before_prompt": "sys_start",
            "after_prompt": "sys_end"
            # 可以根据需要添加更多映射
        }
        # 默认为 sys_start
        return position_map.get(pos_value, "sys_start")
    
    def process_match(self, keys, keysecondary) -> str:
        """处理key和keysecondary，转换为匹配规则格式"""
        if not keys:
            return ""
        
        # 处理主关键词 - 确保keys是列表
        if isinstance(keys, str):
            keys = [keys]
        elif not isinstance(keys, list):
            try:
                keys = list(keys)
            except:
                keys = [str(keys)]
        
        primary = "&".join(str(k) for k in keys if k)
        
        # 处理次要关键词(排除项) - 确保keysecondary是列表
        if isinstance(keysecondary, str):
            keysecondary = [keysecondary]
        elif keysecondary and not isinstance(keysecondary, list):
            try:
                keysecondary = list(keysecondary)
            except:
                keysecondary = [str(keysecondary)]
        
        secondary = ""
        if keysecondary:
            secondary = "&".join(str(k) for k in keysecondary if k)
        
        # 组合
        if primary and secondary:
            return f"{primary}~{secondary}"
        return primary
    
    def process_entry(self, entry_id: Union[str, int], entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单个条目并准备转换后的触发器数据"""
        try:
            # 验证条目
            if not isinstance(entry, dict):
                logger.warning(f"警告: 条目 {entry_id} 不是有效的字典格式，已跳过")
                return None
            
            # 处理基本字段映射
            raw_entry_name = entry.get("comment", f"entry_{entry_id}")
            
            # 处理匹配规则 - 使用 'keys' 和 'secondary_keys'
            keys = entry.get("keys", []) 
            keysecondary = entry.get("secondary_keys", []) 
            raw_entry_match = self.process_match(keys, keysecondary)
            
            # 处理位置 - 使用 'position'
            raw_entry_position = self.convert_position(entry.get("position", "after_char")) 
            
            # 处理内容
            raw_entry_content = self.clean_content(entry.get("content", ""))
            
            # 处理优先级 (100 - order) - 使用 'insertion_order'
            entry_order = entry.get("insertion_order", 100) 
            if not isinstance(entry_order, (int, float)):
                try:
                    entry_order = float(entry_order)
                except ValueError: 
                    logger.warning(f"条目 {entry_id} 的 insertion_order '{entry_order}' 无效，使用默认值 100")
                    entry_order = 100
            entry_priority = 100 - entry_order

            # 从 extensions 获取 prevent_recursion 和 probability
            extensions = entry.get("extensions", {})
            entry_block = bool(extensions.get("prevent_recursion", False)) 
            
            entry_probability_raw = extensions.get("probability", 100) 
            if not isinstance(entry_probability_raw, (int, float)):
                try:
                    entry_probability_raw = float(entry_probability_raw)
                except ValueError: 
                    logger.warning(f"条目 {entry_id} 的 probability '{entry_probability_raw}' 无效，使用默认值 100")
                    entry_probability_raw = 100
            entry_probability = max(0, min(entry_probability_raw, 100)) / 100

            # 检查是否禁用 - 使用 'enabled' (注意逻辑反转)
            if not entry.get("enabled", True): 
                logger.info(f"跳过禁用的条目: {entry_id} ({raw_entry_name})")
                return None

            # --- 应用 quote_value ---
            quoted_entry_name = self.quote_value(raw_entry_name)
            quoted_entry_match = self.quote_value(raw_entry_match)
            quoted_entry_conditional = self.quote_value("") 
            quoted_entry_content = self.quote_value(raw_entry_content)
            quoted_entry_type = self.quote_value("keywords") # 对硬编码的 "keywords" 应用
            quoted_entry_position = self.quote_value(raw_entry_position) # 对转换后的 position 值应用
                
            # 构建触发器 - 使用带引号的值
            trigger = {
                "name": quoted_entry_name,
                "type": quoted_entry_type, # 使用带引号的 type
                "match": quoted_entry_match,
                "conditional": quoted_entry_conditional,
                "priority": entry_priority, # 数字不需要引号
                "block": entry_block,       # 布尔值不需要引号
                "probability": entry_probability, # 数字不需要引号
                "position": quoted_entry_position, # 使用带引号的 position
                "content": quoted_entry_content
            }
            
            logger.debug(f"成功处理条目 {entry_id}: {raw_entry_name}") # 日志中使用原始名称
            return trigger
            
        except Exception as e:
            logger.error(f"处理条目 {entry_id} 时出错: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    def extract_entries_from_json(self, data: Dict[str, Any], source_file: str = "") -> List[Dict[str, Any]]:
        """从JSON数据中提取条目"""
        triggers = []
        
        # 情况 -1: 检查 data['data']['character_book']['entries'] 路径 (新添加)
        if 'data' in data and isinstance(data['data'], dict) and \
           'character_book' in data['data'] and isinstance(data['data']['character_book'], dict) and \
           'entries' in data['data']['character_book'] and isinstance(data['data']['character_book']['entries'], list):
            
            entries_list = data['data']['character_book']['entries']
            logger.debug(f"找到 data['data']['character_book']['entries'] 数组，包含 {len(entries_list)} 个条目")
            
            for i, entry in enumerate(entries_list):
                # 使用 entry 的 'id' 字段（如果存在）作为 entry_id，否则使用索引 i
                entry_id_from_json = entry.get('id', i) 
                trigger = self.process_entry(entry_id_from_json, entry)
                if trigger:
                    triggers.append(trigger)
                    self.entries_processed += 1
            
            return triggers

        # 情况0: 有character_book.entries数组，新的SillyTavern格式 (保持原有逻辑作为备选)
        if 'character_book' in data and isinstance(data['character_book'], dict) and 'entries' in data['character_book'] and isinstance(data['character_book']['entries'], list):
            entries_list = data['character_book']['entries']
            logger.debug(f"找到character_book.entries数组，包含 {len(entries_list)} 个条目")
            
            for i, entry in enumerate(entries_list):
                trigger = self.process_entry(i, entry)
                if trigger:
                    triggers.append(trigger)
                    self.entries_processed += 1
            
            return triggers
        
        # 情况1: 有entries字段，标准SillyTavern格式 (保持原有逻辑作为备选)
        if 'entries' in data and isinstance(data['entries'], dict):
            entries = data['entries']
            logger.debug(f"找到entries字段，包含 {len(entries)} 个条目")
            
            for entry_id, entry in entries.items():
                trigger = self.process_entry(entry_id, entry)
                if trigger:
                    triggers.append(trigger)
                    self.entries_processed += 1
            
            return triggers
        
        # 情况2: JSON具有常见的条目属性，作为单个条目处理
        if any(key in data for key in ["keys", "comment", "content", "insertion_order"]):
            logger.debug("JSON具有条目属性，作为单个条目处理")
            trigger = self.process_entry("1", data)
            if trigger:
                triggers.append(trigger)
                self.entries_processed += 1
            return triggers
        
        # 情况3: 尝试将JSON的每个顶级字段作为独立条目处理
        logger.debug("尝试将顶级字段作为独立条目处理")
        found_entries = False
        for key, value in data.items():
            if isinstance(value, dict):
                trigger = self.process_entry(key, value)
                if trigger:
                    triggers.append(trigger)
                    self.entries_processed += 1
                    found_entries = True
        
        if found_entries:
            return triggers
        
        # 情况4: 如果值是数组，尝试处理数组中的每个项
        array_fields = [(k, v) for k, v in data.items() if isinstance(v, list)]
        for field_name, array in array_fields:
            for i, item in enumerate(array):
                if isinstance(item, dict):
                    trigger = self.process_entry(f"{field_name}_{i+1}", item)
                    if trigger:
                        triggers.append(trigger)
                        self.entries_processed += 1
                        found_entries = True
        
        if found_entries:
            return triggers
        
        # 情况5: 所有方法都失败，创建一个包含整个JSON的默认条目
        logger.debug("未找到条目结构，将整个JSON作为单个条目处理")
        basename = os.path.basename(source_file) if source_file else "unknown"
        name = os.path.splitext(basename)[0]
        
        default_entry = {
            "keys": [name],
            "comment": f"从{basename}生成",
            "content": json.dumps(data, ensure_ascii=False, indent=2),
            "insertion_order": 100,
            "extensions": {
                "probability": 100
            }
        }
        
        trigger = self.process_entry("default", default_entry)
        if trigger:
            triggers.append(trigger)
            self.entries_processed += 1
        
        return triggers
    
    def convert_json_to_yaml(self, json_data: Dict[str, Any], source_file: str = "") -> bool:
        """将JSON数据转换为YAML格式"""
        try:
            # 重置状态
            self.yaml_data = {
                "world_state": {},
                "user_state": [],
                "trigger": []
            }
            self.entries_processed = 0
            
            # 提取并处理条目
            triggers = self.extract_entries_from_json(json_data, source_file)
            
            # 添加到YAML数据结构中
            self.yaml_data["trigger"] = triggers
            
            # 检查是否有有效条目
            if not self.yaml_data["trigger"]:
                logger.warning("警告: 没有生成有效的触发器数据")
                # 添加一个默认条目
                self.yaml_data["trigger"].append({
                    "name": "默认条目",
                    "type": "keywords",
                    "match": "",
                    "conditional": "",
                    "priority": 50,
                    "block": False,
                    "probability": 1.0,
                    "position": "sys_start",
                    "content": "无法从源数据提取有效内容，这是一个自动生成的默认条目。"
                })
                self.entries_processed += 1
            
            logger.info(f"总共处理了 {self.entries_processed} 个条目")
            return True
        
        except Exception as e:
            logger.error(f"转换JSON到YAML时出错: {e}")
            logger.debug(traceback.format_exc())
            return False
    
    def save_yaml_to_file(self, output_file: str) -> bool:
        """将YAML数据保存到文件"""
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                logger.debug(f"创建输出目录: {output_dir}")
            
            # 使用自定义 Dumper 来强制字符串使用双引号
            class ForceDoubleQuoteDumper(yaml.SafeDumper):
                def represent_scalar(self, tag, value, style=None):
                    if isinstance(value, str):
                        # 如果我们已经手动加了引号和转义，直接返回
                        if value.startswith('"') and value.endswith('"'):
                            if '\\n' in value[1:-1]: # 如果包含转义后的换行符，使用字面量块风格
                                style = '|'
                                processed_value = value[1:-1].replace('\\n', '\n').replace('\\"', '"')
                                return super().represent_scalar(tag, processed_value, style=style)
                            else:
                                style = '"'
                                return super().represent_scalar(tag, value[1:-1], style=style)
                    return super().represent_scalar(tag, value, style)

            # 序列化YAML
            yaml_str = yaml.dump(
                self.yaml_data, 
                Dumper=ForceDoubleQuoteDumper, 
                allow_unicode=True, 
                sort_keys=False, 
                default_flow_style=False,
                width=float('inf')
            )
            logger.debug(f"YAML序列化结果大小: {len(yaml_str)} 字节")
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as yaml_file:
                yaml_file.write(yaml_str)
            
            # 验证文件写入
            if not os.path.exists(output_file):
                logger.error(f"错误: 文件未创建: {output_file}")
                return False
            
            file_size = os.path.getsize(output_file)
            if file_size == 0:
                logger.error(f"错误: 文件为空: {output_file}")
                return False
            
            logger.info(f"成功保存YAML文件: {output_file}, 大小: {file_size} 字节")
            return True
            
        except Exception as e:
            logger.error(f"保存YAML文件时出错: {e}")
            logger.debug(traceback.format_exc())
            return False

def json_to_lorebook_yaml(json_input: Union[str, Dict[str, Any]], output_file: Optional[str] = None) -> Optional[str]:
    """
    将JSON文件或数据转换为astrbot_plugin_lorebook_lite插件支持的YAML格式
    
    参数:
    json_input: JSON文件路径(str) 或 JSON数据(dict)
    output_file: 输出YAML文件的路径
    
    返回:
    成功时返回输出文件路径，失败时返回None
    """
    try:
        source_description = ""
        data = None
        
        if isinstance(json_input, str):
            # Input is a file path
            json_file = json_input
            source_description = f"JSON文件: {json_file}"
            logger.info(f"开始处理 {source_description}")
            
            # 确保文件存在
            if not os.path.isfile(json_file):
                logger.error(f"错误: 找不到文件 {json_file}")
                return None
            
            # 读取JSON文件
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"成功读取JSON文件，大小: {os.path.getsize(json_file)} 字节")
            except json.JSONDecodeError as e:
                logger.error(f"错误: JSON解析失败 - {e}")
                return None
            except Exception as e:
                logger.error(f"错误: 读取文件时出错 - {e}")
                return None
                
        elif isinstance(json_input, dict):
            # Input is a dictionary
            data = json_input
            source_description = "JSON数据字典"
            logger.info(f"开始处理 {source_description}")
            logger.debug(f"接收到的JSON数据大小: {len(json.dumps(data))} 字节")
            
        else:
            logger.error(f"错误: 无效的输入类型 {type(json_input)}，需要 str 或 dict")
            return None

        # 确定输出文件路径
        if output_file is None:
            if isinstance(json_input, str): # Use filename if input was a file
                basename = os.path.basename(json_input)
                name = os.path.splitext(basename)[0]
            else: # Generate a default name if input was data
                name = "converted_data" 
            output_dir = os.path.join("data", "lorebooks")
            output_file = os.path.join(output_dir, f"{name}.yaml")
        
        # 创建转换器实例并进行转换
        converter = LoreBookConverter()
        
        # Pass the source description (filename or dict info) for potential use in default entry generation
        source_ref = json_input if isinstance(json_input, str) else "" 
        
        if converter.convert_json_to_yaml(data, source_ref):
            if converter.save_yaml_to_file(output_file):
                logger.info(f"从 {source_description} 到YAML转换成功: {output_file}")
                return output_file
        
        logger.error(f"从 {source_description} 到YAML转换失败")
        return None
        
    except Exception as e:
        logger.error(f"处理过程中出现未处理的异常: {e}")
        logger.debug(traceback.format_exc())
        return None

def main():
    """命令行入口点"""
    parser = argparse.ArgumentParser(description='将JSON文件转换为astrbot_plugin_lorebook_lite插件支持的YAML格式')
    parser.add_argument('json_file', type=str, help='输入的JSON文件路径')
    parser.add_argument('--output', '-o', type=str, help='输出YAML文件路径', default=None)
    
    args = parser.parse_args()
    
    # 执行转换
    result = json_to_lorebook_yaml(args.json_file, args.output)
    if result:
        print(f"转换成功，YAML文件已保存到: {result}")
    else:
        print("转换失败，请查看日志获取详细信息")
        sys.exit(1)

if __name__ == "__main__":
    main()