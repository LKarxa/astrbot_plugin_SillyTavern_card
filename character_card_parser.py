# character_card_parser.py
import png
import base64
import json
import io
import struct
import zlib  # Needed for CRC calculation
from typing import List, Tuple, Optional

# Import astrbot logger
from astrbot.api import logger

def _find_chunks(chunks: List[Tuple[bytes, bytes]], name: bytes) -> List[Tuple[bytes, bytes]]:
    """查找指定名称的 PNG 块"""
    return [chunk for chunk in chunks if chunk[0] == name]

def _decode_text_chunk(chunk_data: bytes) -> Tuple[str, str]:
    """解码 tEXt 块数据"""
    keyword, text = chunk_data.split(b'\x00', 1)
    return keyword.decode('iso-8859-1'), text.decode('iso-8859-1')

def _encode_text_chunk(keyword: str, text: str) -> bytes:
    """编码 tEXt 块数据"""
    return keyword.encode('iso-8859-1') + b'\x00' + text.encode('iso-8859-1')

def write_metadata(image_bytes: bytes, data: str) -> bytes:
    """
    将角色元数据写入 PNG 图片字节流。
    同时写入 'chara' (v2) 和 'ccv3' (v3) 块。
    This version manually reconstructs the PNG from chunks.

    Args:
        image_bytes: PNG 图片的字节流。
        data: 要写入的角色数据 (JSON 字符串)。

    Returns:
        带有元数据的 PNG 图片字节流。

    Raises:
        png.Error: 如果 PNG 无效或缺少 IHDR 块。
        ValueError: 如果输入数据不是有效的 JSON 字符串 (当尝试创建 v3 块时)。
    """
    # Check PNG signature
    if not image_bytes.startswith(png.signature):
        raise png.Error("Not a valid PNG file (incorrect signature)")

    reader = png.Reader(bytes=image_bytes)
    try:
        # Read chunks without processing pixel data
        original_chunks = list(reader.chunks())
    except png.Error as e:
        logger.error(f"Error reading PNG chunks: {e}")
        raise

    # Filter out old 'chara' and 'ccv3' tEXt chunks
    new_chunks = []
    for chunk_type, chunk_data in original_chunks:
        if chunk_type == b'tEXt':
            try:
                keyword, _ = _decode_text_chunk(chunk_data)
                if keyword.lower() not in ('chara', 'ccv3'):
                    new_chunks.append((chunk_type, chunk_data))
            except Exception as e:  # If decoding fails, keep the original chunk
                logger.warning(f"Failed to decode tEXt chunk during filtering, keeping original: {e}")
                new_chunks.append((chunk_type, chunk_data))
        else:
            # Keep all non-tEXt chunks (including IHDR, IDAT, IEND, etc.)
            new_chunks.append((chunk_type, chunk_data))

    # Prepare v2 data
    base64_encoded_v2_data = base64.b64encode(data.encode('utf-8')).decode('ascii')
    v2_chunk_data = _encode_text_chunk('chara', base64_encoded_v2_data)
    v2_chunk_tuple = (b'tEXt', v2_chunk_data)

    # Prepare v3 data
    v3_chunk_tuple = None
    try:
        v3_data_dict = json.loads(data)
        v3_data_dict['spec'] = 'chara_card_v3'
        v3_data_dict['spec_version'] = '3.0'
        v3_json_string = json.dumps(v3_data_dict)
        base64_encoded_v3_data = base64.b64encode(v3_json_string.encode('utf-8')).decode('ascii')
        v3_chunk_data = _encode_text_chunk('ccv3', base64_encoded_v3_data)
        v3_chunk_tuple = (b'tEXt', v3_chunk_data)
    except json.JSONDecodeError as e:
        logger.warning(f"Could not create v3 chunk, invalid JSON data: {e}")
    except Exception as e:
        logger.warning(f"Could not create v3 chunk: {e}")

    # Find IEND chunk index to insert before it
    iend_index = -1
    for i, (chunk_type, _) in enumerate(new_chunks):
        if chunk_type == b'IEND':
            iend_index = i
            break

    if iend_index != -1:
        # Insert new chunks before IEND
        insert_pos = iend_index
        new_chunks.insert(insert_pos, v2_chunk_tuple)
        if v3_chunk_tuple:
            new_chunks.insert(insert_pos + 1, v3_chunk_tuple)
    else:
        logger.warning("IEND chunk not found. Appending metadata chunks.")
        new_chunks.append(v2_chunk_tuple)
        if v3_chunk_tuple:
            new_chunks.append(v3_chunk_tuple)
        # Consider adding a dummy IEND if missing, but for now just append.

    # Manually reconstruct the PNG byte stream
    output_buffer = io.BytesIO()
    output_buffer.write(png.signature)  # Write the signature first

    for chunk_type, chunk_data in new_chunks:
        # Pack length (Big-endian unsigned integer, 4 bytes)
        output_buffer.write(struct.pack('>I', len(chunk_data)))
        # Write chunk type
        output_buffer.write(chunk_type)
        # Write chunk data
        output_buffer.write(chunk_data)
        # Calculate and write CRC (Big-endian unsigned integer, 4 bytes)
        # CRC is calculated over the chunk type and chunk data bytes
        crc = zlib.crc32(chunk_type + chunk_data)
        output_buffer.write(struct.pack('>I', crc))

    return output_buffer.getvalue()

def read_metadata(image_bytes: bytes) -> Optional[str]:
    """
    从 PNG 图片字节流中读取角色元数据。
    优先读取 V3 ('ccv3')，其次读取 V2 ('chara')。

    Args:
        image_bytes: PNG 图片的字节流。

    Returns:
        角色数据字符串 (JSON)，如果未找到则返回 None。

    Raises:
        png.Error: 如果输入字节不是有效的 PNG。
        ValueError: 如果找到的块数据无法解码。
    """
    try:
        reader = png.Reader(bytes=image_bytes)
        chunks = list(reader.chunks())
    except png.Error as e:
        logger.error(f"Error reading PNG: {e}")
        raise

    text_chunks_data = {}
    for chunk_type, chunk_data in chunks:
        if chunk_type == b'tEXt':
            try:
                keyword, text = _decode_text_chunk(chunk_data)
                text_chunks_data[keyword.lower()] = text
            except Exception as e:
                logger.warning(f"Could not decode tEXt chunk: {e}")
                continue  # 跳过无法解码的块

    if not text_chunks_data:
        logger.info("PNG metadata does not contain any text chunks.")
        return None

    # 优先 V3
    if 'ccv3' in text_chunks_data:
        try:
            return base64.b64decode(text_chunks_data['ccv3']).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Error decoding base64 for ccv3 chunk: {e}")

    # 其次 V2
    if 'chara' in text_chunks_data:
        try:
            return base64.b64decode(text_chunks_data['chara']).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Error decoding base64 for chara chunk: {e}")

    logger.info("PNG metadata does not contain any character data ('chara' or 'ccv3').")
    return None

def parse_card(card_path: str, file_format: str = 'png') -> Optional[str]:
    """
    解析卡片图片文件并返回角色元数据。

    Args:
        card_path: 卡片图片的文件路径。
        file_format: 文件格式 (目前仅支持 'png')。

    Returns:
        角色数据字符串 (JSON)，如果未找到或格式不支持则返回 None。

    Raises:
        FileNotFoundError: 如果文件路径不存在。
        ValueError: 如果文件格式不受支持或解码失败。
        png.Error: 如果文件不是有效的 PNG。
    """
    if file_format.lower() != 'png':
        raise ValueError(f"Unsupported format: {file_format}. Only 'png' is supported.")

    try:
        with open(card_path, 'rb') as f:
            image_bytes = f.read()
        return read_metadata(image_bytes)
    except FileNotFoundError:
        logger.error(f"Error: File not found at {card_path}")
        raise
    except (png.Error, ValueError) as e:
        logger.error(f"Error parsing card {card_path}: {e}")
        raise  # 重新抛出异常，让调用者处理

# --- 示例用法 ---
if __name__ == '__main__':
    # 注意：你需要一个名为 'pypng' 的库。请使用 pip install pypng 安装。

    input_png_path = 'output_card.png'  # 指定包含元数据的输入 PNG 文件路径
    output_json_path = 'extracted_character_data.json'  # 输出 JSON 文件路径

    print(f"Attempting to read metadata from PNG card: {input_png_path}")

    try:
        # 1. 从 PNG 文件解析元数据
        character_json_string = parse_card(input_png_path)

        if character_json_string:
            print("Successfully read metadata from PNG.")
            # 2. 将提取的 JSON 字符串写入文件
            print(f"Writing extracted data to JSON file: {output_json_path}")
            try:
                # 尝试美化 JSON 输出
                parsed_data = json.loads(character_json_string)
                with open(output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                print("Warning: Could not parse the extracted data as JSON. Writing raw string.")
                # 如果无法解析为 JSON（理论上不应发生，除非元数据损坏），则直接写入原始字符串
                with open(output_json_path, 'w', encoding='utf-8') as f:
                    f.write(character_json_string)
            print("Extracted data written to JSON successfully.")
        else:
            print(f"No character metadata found in {input_png_path} or error reading.")

    except FileNotFoundError:
        print(f"Error: Input PNG file '{input_png_path}' not found.")
    except (png.Error, ValueError) as e:
        print(f"Error parsing PNG card {input_png_path}: {e}")
    except IOError as e:
        print(f"Error writing JSON file '{output_json_path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
