import whisper
import os
from audio_backend.app.core.config import config



model_name = config.MODEL_NAME
cache_dir = os.path.expanduser("~/.cache/whisper")
model_url = whisper._MODELS[model_name]
model_file = os.path.join(cache_dir, os.path.basename(model_url))

print("📁 Whisper 模型文件路径：", model_file)
# ✅ 预加载 Whisper（默认最常用）
whisper_model = whisper.load_model(config.MODEL_NAME).to("cpu")


def process_audio(file_path: str, selected_model: str):
    """ 根据用户选择的模型处理音频，未来可以方便扩展 """

    match selected_model.lower():
        case "whisper":
            model = whisper_model  # ✅ 使用预加载的 Whisper
            result = model.transcribe(
                file_path,
                word_timestamps=True,
                
            )
            transcript = result["text"]
            
            word_timestamps = []
            for segment in result.get("segments", []):
                    for word in segment.get("words", []):
                        word_timestamps.append({
                          "word": word["word"].strip(),
                          "start": word["start"],
                          "end": word["end"]
                       })

            # ✅ 语言检测
            detected_lang = result["language"]
            lang_mapping = {"en": "ENGLISH", "es": "SPANISH"}
            detected_lang_name = lang_mapping.get(detected_lang, "Unknown")

            # ✅ 翻译文本
            translated_result = model.transcribe(file_path, task="translate", language="zh")
            translated_text = translated_result["text"]
            
            return transcript, translated_text, detected_lang_name, word_timestamps, f"Processed with {selected_model}"
        
        case "deepspeech":
            
            return None, None, None, "DeepSpeech selected, but processing not implemented yet."
        
        case "google-stt":
            return None, None, None, "Google STT selected, processing not implemented yet."

        case _:
            return None, None, None, f"Unknown model: {selected_model}, no processing done."

