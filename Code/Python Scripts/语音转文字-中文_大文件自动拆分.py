"""大文件音频分片转录工具。

处理规则：
1. 通过弹窗输入本地文件或目录。
2. 不需要分割的文件直接把转录文本保存到桌面。
3. 超过分片时长的文件在桌面创建唯一工作目录，再提取为 FLAC 分片并转录。
4. 不指定语言，让 faster-whisper 对每个分片自动识别语言。
5. 分片文本和最终合并文本不包含时间码。

依赖：
    python -m pip install faster-whisper zhconv
    ffmpeg 和 ffprobe 需要在 py3.10 中，见 blog 的 ffmpeg 安装说明
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from faster_whisper import WhisperModel

try:
    from zhconv import convert
except ImportError:
    convert = None


MEDIA_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",
    ".wma",
    ".webm",
    ".mp4",
    ".m4v",
    ".mkv",
    ".avi",
    ".mov",
    ".mpeg",
    ".mpg",
    ".ts",
)
DEFAULT_SEGMENT_MINUTES = 30


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def atomic_write_text(path: Path, text: str) -> None:
    """写入临时文件后替换目标，避免中断时留下半个结果文件。"""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def create_workspace(input_path: Path) -> Path:
    """在桌面创建以输入文件名为基础的唯一目录，并保留它。"""
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)

    # 文件名通常不会包含斜杠；额外清理控制字符，避免生成不可用目录名。
    stem = re.sub(r"[\x00-\x1f/]", "_", input_path.stem).strip() or "transcription"
    candidate = desktop / stem
    if not candidate.exists():
        candidate.mkdir()
        return candidate

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for _ in range(100):
        extra = f"_{timestamp}_{uuid.uuid4().hex[:6]}"
        candidate = desktop / f"{stem}{extra}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue

    raise RuntimeError(f"无法在桌面创建唯一工作目录：{stem}")


def prompt_for_source() -> str | None:
    """显示一个输入框；取消时返回 None。"""
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError as error:
        raise RuntimeError("当前 Python 没有 tkinter，无法显示输入弹窗。") from error

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = simpledialog.askstring(
            "要转录的文件或目录",
            "请输入本地文件路径或目录路径：",
            parent=root,
        )
    finally:
        try:
            # 在开始耗时转录前，让系统先处理窗口隐藏和关闭事件。
            root.withdraw()
            root.update_idletasks()
            root.update()
        finally:
            root.destroy()

    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def find_media_files(directory: Path) -> list[Path]:
    """查找目录第一层中的音视频文件。"""
    return sorted(
        (
            path.resolve()
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"找不到 {name}，请确认它已安装并且在 PATH 中。")
    return path


def get_media_duration(file_path: Path, ffprobe_path: str) -> float:
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    value = float(result.stdout.strip())
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"无法读取有效的视频时长：{file_path}")
    return value


def split_to_audio_parts(
    file_path: Path,
    workspace: Path,
    segment_seconds: int,
    ffmpeg_path: str,
) -> list[Path]:
    """只提取第一条音频流并切成 FLAC，避免复制视频容器的关键帧问题。"""
    pattern = workspace / "part_%04d.flac"
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(file_path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "flac",
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        str(pattern),
    ]
    print(f"正在拆分音频，每段约 {segment_seconds // 60} 分钟……")
    subprocess.run(command, check=True)

    parts = sorted(workspace.glob("part_*.flac"))
    parts = [part for part in parts if part.stat().st_size > 0]
    if not parts:
        raise RuntimeError("FFmpeg 没有生成任何音频分片，请检查输入文件的音频流。")
    return parts


def transcribe_audio_file(model: WhisperModel, input_path: Path) -> str:
    """自动识别当前分片语言，返回不含时间码的纯文本。"""
    start_time = time.time()
    segments, info = model.transcribe(
        str(input_path),
        language=None,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    duration = info.duration or 0
    print(f"    音频时长：{format_seconds(duration)}")

    text_parts: list[str] = []
    last_percent = -1
    for segment in segments:
        text = segment.text.strip()
        if text:
            text_parts.append(text)

        if duration <= 0:
            continue
        progress = min(max(segment.end / duration, 0), 1)
        percent = int(progress * 100)
        if percent == last_percent:
            continue
        elapsed = time.time() - start_time
        estimated_total = elapsed / progress if progress > 0 else 0
        remaining = max(estimated_total - elapsed, 0)
        print(
            f"\r    分片进度：{percent:3d}% "
            f"({format_seconds(segment.end)} / {format_seconds(duration)}) "
            f"已用 {format_seconds(elapsed)} 预计剩余 {format_seconds(remaining)}",
            end="",
            flush=True,
        )
        last_percent = percent
    print()
    return "\n".join(text_parts)


def simplify_text(text: str) -> str:
    if convert:
        return convert(text, "zh-cn")
    print("未安装 zhconv，跳过繁简转换。")
    return text


def transcribe_part(model: WhisperModel, part_path: Path, force: bool) -> str:
    text_path = part_path.with_suffix(".txt")
    if text_path.exists() and not force:
        print(f"    已存在分片文本，跳过：{text_path.name}")
        return text_path.read_text(encoding="utf-8")

    text = simplify_text(transcribe_audio_file(model, part_path))
    atomic_write_text(text_path, text + ("\n" if text else ""))
    return text


def process_file(
    model: WhisperModel,
    input_path: Path,
    ffmpeg_path: str,
    ffprobe_path: str,
    segment_seconds: int,
    force: bool,
) -> Path:
    duration = get_media_duration(input_path, ffprobe_path)
    print(f"原文件时长：{format_seconds(duration)}")

    if duration > segment_seconds:
        workspace = create_workspace(input_path)
        output_path = workspace / f"{input_path.stem}.txt"
        print(f"工作目录（保留不删除）：{workspace}")
        parts = split_to_audio_parts(
            input_path,
            workspace,
            segment_seconds,
            ffmpeg_path,
        )
        texts: list[str] = []
        for index, part_path in enumerate(parts, 1):
            print(f"  正在转录分片 ({index}/{len(parts)})：{part_path.name}")
            texts.append(transcribe_part(model, part_path, force))
        final_text = "\n\n".join(text.strip() for text in texts if text.strip())
    else:
        workspace = None
        desktop = Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        output_path = desktop / f"{input_path.stem}.txt"
        if output_path.exists() and not force:
            raise FileExistsError(
                f"最终文本已存在：{output_path}\n"
                "如需覆盖，请重新运行并加上 --force。"
            )
        print("文件没有超过分片时长，直接转录。")
        final_text = simplify_text(transcribe_audio_file(model, input_path))

    atomic_write_text(output_path, final_text + ("\n" if final_text else ""))
    print(f"转录完成：{output_path}")
    if workspace:
        print(f"分片和中间文本仍保留在：{workspace}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="大文件自动拆分并转录为纯文本")
    parser.add_argument(
        "--model",
        default="medium",
        choices=("tiny", "base", "small", "medium", "large-v3"),
        help="faster-whisper 模型，默认 medium",
    )
    parser.add_argument(
        "--segment-minutes",
        type=int,
        default=DEFAULT_SEGMENT_MINUTES,
        help="超过此时长才拆分，默认 30 分钟",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖工作目录中已经存在的分片文本和最终文本",
    )
    args = parser.parse_args()

    if args.segment_minutes <= 0:
        raise SystemExit("--segment-minutes 必须大于 0。")

    try:
        source = prompt_for_source()
        if source is None:
            print("已取消转录。")
            return
        if not source:
            raise RuntimeError("没有输入文件或目录。")

        ffmpeg_path = require_tool("ffmpeg")
        ffprobe_path = require_tool("ffprobe")
        input_path = Path(source).expanduser().resolve()
        if input_path.is_file():
            if input_path.suffix.lower() not in MEDIA_EXTENSIONS:
                raise RuntimeError(f"不支持的音视频格式：{input_path.suffix or '无扩展名'}")
            jobs = [input_path]
        elif input_path.is_dir():
            media_files = find_media_files(input_path)
            if not media_files:
                raise RuntimeError(f"目录第一层没有找到支持的音视频文件：{input_path}")
            print(f"目录中找到 {len(media_files)} 个音视频文件。")
            jobs = media_files
        else:
            raise RuntimeError(f"输入路径不存在：{input_path}")

        print(f"正在加载 Whisper {args.model} 模型……")
        model = WhisperModel(args.model, compute_type="int8")
        failures: list[str] = []
        for index, input_path in enumerate(jobs, 1):
            if len(jobs) > 1:
                print(f"\n===== 正在处理 ({index}/{len(jobs)})：{input_path.name} =====")
            try:
                process_file(
                    model,
                    input_path,
                    ffmpeg_path,
                    ffprobe_path,
                    args.segment_minutes * 60,
                    args.force,
                )
            except Exception as error:
                failures.append(f"{input_path.name}：{error}")
                print(f"处理失败：{input_path.name}：{error}")

        if failures:
            details = "\n".join(f"- {failure}" for failure in failures)
            raise RuntimeError(f"有 {len(failures)} 个任务失败：\n{details}")
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"外部命令执行失败（退出码 {error.returncode}）。"
            "工作目录已保留，请检查其中的分片和命令输出。"
        ) from error
    except Exception as error:
        raise SystemExit(f"转录失败：{error}") from error


if __name__ == "__main__":
    main()
