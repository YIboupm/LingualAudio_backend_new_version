import torch
import whisper
from torch import nn

class WhisperEncoderWrapper(nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.conv1 = encoder.conv1
        self.conv2 = encoder.conv2
        self.encoder_blocks = encoder.blocks
        self.positional_embedding = encoder.positional_embedding
        self.ln_post = encoder.ln_post

    def forward(self, mel):
        x = self.conv1(mel)
        x = self.conv2(x)
        x = x.permute(0, 2, 1)  # (batch, time, channel)
        x = x + self.positional_embedding[:x.shape[1]]
        for block in self.encoder_blocks:
            x = block(x)
        x = self.ln_post(x)
        return x

# 加载 Whisper 模型
model = whisper.load_model("large-v3")

# 构造 encoder-only 模型
encoder_model = WhisperEncoderWrapper(model.encoder)

# 构造 dummy 梅尔输入
dummy_input = torch.randn(1, 128, 3000)

# 导出为 ONNX
torch.onnx.export(
    encoder_model,
    dummy_input,
    "whisper_encoder_only.onnx",
    input_names=["mel"],
    output_names=["encoded"],
    dynamic_axes={"mel": {0: "batch", 2: "n_frames"}},
    opset_version=14
)

print("✅ 成功导出 whisper_encoder_only.onnx，可在 Netron 打开查看结构！")
