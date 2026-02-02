import os
import re
import pykakasi
from mutagen import File
from mutagen.id3 import ID3, USLT

# ================= 配置区域 =================
TARGET_DIR = r"PATH"
# 确认无误后，将下面改为 True
WRITE_TO_FILE = True 
# ===========================================

# 初始化转换器
kks = pykakasi.kakasi()
conversion = kks.convert

# === 核心修改点 ===
# 新的正则：匹配 [汉字/假名/迭代符号] + [括号] + [假名] + [反括号]
# 这样能识别 "戸惑う(とまどう)" 或 "笑っ(わらっ)" 这种混合结构
# \u3005 代表 "々" 这种叠字符号
EXISTING_FURIGANA_REGEX = re.compile(r'([\u4e00-\u9fff\u3040-\u30ff\u3005]+[\(\（][\u3040-\u30ff]+[\)\）])')

def has_kanji(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def has_kana(text):
    return bool(re.search(r'[\u3040-\u30ff]', text))

def add_furigana_basic(text):
    """
    基础注音逻辑
    """
    result = conversion(text)
    new_line = ""
    for item in result:
        orig = item['orig']
        hira = item['hira']
        
        # 仅当包含汉字且读音不同时加括号
        # 比如 "アイドル" -> orig=hira -> 不加括号
        if has_kanji(orig) and orig != hira:
            new_line += f"{orig}({hira})"
        else:
            new_line += orig
    return new_line

def add_furigana_smart(text):
    """
    智能注音逻辑：先切分，保护已有注音，只处理未注音部分
    """
    # 使用正则 split，保留捕获组（即保留匹配到的已注音部分）
    parts = EXISTING_FURIGANA_REGEX.split(text)
    
    final_line = []
    for part in parts:
        # 如果部分为空（split产生），跳过
        if not part:
            continue
            
        # 检查这部分是否完整匹配"已注音格式"
        # fullmatch 确保完全匹配，而不是部分匹配
        if EXISTING_FURIGANA_REGEX.fullmatch(part):
            final_line.append(part) # 是已注音的词（如 "気持ち(きもち)"），原样保留
        else:
            # 是未注音的普通文本，进行注音处理
            final_line.append(add_furigana_basic(part))
            
    return "".join(final_line)

def process_lyrics_text(lyrics_str):
    if not lyrics_str: return None

    lines = lyrics_str.split('\n')
    new_lines = []
    
    time_pattern = re.compile(r'^(\[[\d:.]+\])(.*)')

    for line in lines:
        line = line.strip()
        match = time_pattern.match(line)
        
        if match:
            timestamp = match.group(1)
            content = match.group(2).strip()
            
            # 只有同时包含 [汉字] 和 [假名] 的行才进入处理流程
            if content and has_kanji(content) and has_kana(content):
                # 智能处理
                new_content = add_furigana_smart(content)
                new_lines.append(f"{timestamp}{new_content}")
                
                # 只有真正发生变化才打印日志
                if content != new_content:
                    print(f"  [修改] {content}")
                    print(f"       -> {new_content}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return '\n'.join(new_lines)

def process_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.cue': return
    print(f"处理文件: {os.path.basename(file_path)}")
    
    try:
        audio = File(file_path)
        if not audio: return
        
        original_lyrics = ""
        lyrics_tag_key = ""
        
        # === 读取 ===
        if ext == '.mp3':
            if audio.tags is None: audio.add_tags()
            uslt_keys = [k for k in audio.tags.keys() if 'USLT' in k]
            if uslt_keys:
                lyrics_tag_key = uslt_keys[0]
                original_lyrics = audio.tags[lyrics_tag_key].text
            else:
                print("  [跳过] 无内嵌歌词")
                return
        elif ext == '.flac':
            if 'LYRICS' in audio.tags:
                lyrics_tag_key = 'LYRICS'
                original_lyrics = audio.tags['LYRICS'][0]
            elif 'UNSYNCEDLYRICS' in audio.tags:
                lyrics_tag_key = 'UNSYNCEDLYRICS'
                original_lyrics = audio.tags['UNSYNCEDLYRICS'][0]
            else:
                print("  [跳过] 无内嵌歌词")
                return
        elif ext == '.wav':
             try:
                 if audio.tags and isinstance(audio.tags, ID3):
                     uslt_keys = [k for k in audio.tags.keys() if 'USLT' in k]
                     if uslt_keys:
                         lyrics_tag_key = uslt_keys[0]
                         original_lyrics = audio.tags[lyrics_tag_key].text
                     else: return
                 else: return
             except: return

        if not original_lyrics: return

        # === 处理 ===
        new_lyrics = process_lyrics_text(original_lyrics)

        # === 写入 ===
        if WRITE_TO_FILE and new_lyrics != original_lyrics:
            if ext == '.mp3' or (ext == '.wav' and isinstance(audio.tags, ID3)):
                current_tag = audio.tags[lyrics_tag_key]
                lang = getattr(current_tag, 'lang', 'eng')
                desc = getattr(current_tag, 'desc', '')
                audio.tags[lyrics_tag_key] = USLT(encoding=3, lang=lang, desc=desc, text=new_lyrics)
            elif ext == '.flac':
                audio.tags[lyrics_tag_key] = new_lyrics
            audio.save()
            print("  [保存成功]")
        else:
            print("  [无变动]")

    except Exception as e:
        print(f"  [错误] {e}")

def main():
    if not os.path.exists(TARGET_DIR):
        print(f"错误: 路径不存在 - {TARGET_DIR}")
        return
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.lower().endswith(('.mp3', '.flac', '.wav')):
                process_file(os.path.join(root, file))

if __name__ == "__main__":
    main()