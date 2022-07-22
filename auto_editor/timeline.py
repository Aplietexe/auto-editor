from __future__ import annotations

from dataclasses import dataclass
from typing import List, NamedTuple, Type, Union
from fractions import Fraction

from auto_editor.ffwrapper import FileInfo
from auto_editor.method import get_speed_list
from auto_editor.objects import (
    AudioObj,
    EllipseObj,
    ImageObj,
    RectangleObj,
    TextObj,
    VideoObj,
    ellipse_builder,
    img_builder,
    parse_dataclass,
    rect_builder,
    text_builder,
)
from auto_editor.utils.func import chunkify, chunks_len
from auto_editor.utils.log import Log
from auto_editor.utils.progressbar import ProgressBar
from auto_editor.utils.types import Args, Chunks


class Clip(NamedTuple):
    start: int
    dur: int
    offset: int
    speed: float
    src: int


Visual = Type[Union[TextObj, ImageObj, RectangleObj, EllipseObj]]
VLayer = List[Union[VideoObj, Visual]]
VSpace = List[VLayer]

ALayer = List[AudioObj]
ASpace = List[ALayer]


def merge_chunks(all_chunks: list[Chunks]) -> Chunks:
    chunks = []
    start = 0
    for _chunks in all_chunks:
        for chunk in _chunks:
            chunks.append((chunk[0] + start, chunk[1] + start, chunk[2]))
        if _chunks:
            start += _chunks[-1][1]

    return chunks


@dataclass
class Timeline:
    inputs: list[FileInfo]
    fps: Fraction
    samplerate: int
    res: tuple[int, int]
    background: str
    v: VSpace
    a: ASpace
    chunks: Chunks | None = None

    @property
    def inp(self) -> FileInfo:
        return self.inputs[0]

    @property
    def timebase(self) -> int:
        return round(self.fps)

    @property
    def end(self) -> int:
        end = 0
        for vclips in self.v:
            if len(vclips) > 0:
                v = vclips[-1]
                if isinstance(v, VideoObj):
                    end = max(end, max(1, round(v.start + (v.dur / v.speed))))
                else:
                    end = max(end, v.start + v.dur)
        for aclips in self.a:
            if len(aclips) > 0:
                a = aclips[-1]
                end = max(end, max(1, round(a.start + (a.dur / a.speed))))

        return end

    def out_len(self) -> float:
        out_len: float = 0
        for vclips in self.v:
            dur: float = 0
            for v_obj in vclips:
                if isinstance(v_obj, VideoObj):
                    dur += v_obj.dur / v_obj.speed
                else:
                    dur += v_obj.dur
            out_len = max(out_len, dur)
        for aclips in self.a:
            dur = 0
            for aclip in aclips:
                dur += aclip.dur / aclip.speed
            out_len = max(out_len, dur)
        return out_len


def clipify(chunks: Chunks, src: int, start: float) -> list[Clip]:
    clips: list[Clip] = []
    # Add "+1" to match how chunks are rendered in 22w18a
    i = 0
    for chunk in chunks:
        if chunk[2] != 99999:
            if i == 0:
                dur = chunk[1] - chunk[0] + 1
                offset = chunk[0]
            else:
                dur = chunk[1] - chunk[0]
                offset = chunk[0] + 1

            if not (len(clips) > 0 and clips[-1].start == round(start)):
                clips.append(Clip(round(start), dur, offset, chunk[2], src))
            start += dur / chunk[2]
            i += 1

    return clips


def make_av(
    all_clips: list[list[Clip]], inputs: list[FileInfo]
) -> tuple[VSpace, ASpace]:
    vclips: VSpace = []

    max_a = 0
    for inp in inputs:
        max_a = max(max_a, len(inp.audios))

    aclips: ASpace = [[] for a in range(max_a)]

    for clips, inp in zip(all_clips, inputs):
        if len(inp.videos) > 0:
            for clip in clips:
                vclip_ = VideoObj(
                    clip.start, clip.dur, clip.offset, clip.speed, clip.src, 0
                )
                if len(vclips) == 0:
                    vclips = [[vclip_]]
                vclips[0].append(vclip_)
        if len(inp.audios) > 0:
            for clip in clips:
                for a, _ in enumerate(inp.audios):
                    aclips[a].append(
                        AudioObj(
                            clip.start, clip.dur, clip.offset, clip.speed, clip.src, a
                        )
                    )

    return vclips, aclips


def make_timeline(
    inputs: list[FileInfo],
    args: Args,
    sr: int,
    progress: ProgressBar,
    temp: str,
    log: Log,
) -> Timeline:

    if inputs:
        fps = inputs[0].get_fps() if args.frame_rate is None else args.frame_rate
        res = inputs[0].get_res() if args.resolution is None else args.resolution
    else:
        fps, res = Fraction(30), (1920, 1080)

    timebase = round(fps)

    def make_layers(inputs: list[FileInfo]) -> tuple[Chunks, VSpace, ASpace]:
        start = 0.0
        all_clips: list[list[Clip]] = []
        all_chunks: list[Chunks] = []

        for i in range(len(inputs)):
            _chunks = chunkify(
                get_speed_list(i, inputs, fps, timebase, args, progress, temp, log)
            )
            all_chunks.append(_chunks)
            all_clips.append(clipify(_chunks, i, start))
            start += chunks_len(_chunks)

        vclips, aclips = make_av(all_clips, inputs)
        return merge_chunks(all_chunks), vclips, aclips

    chunks, vclips, aclips = make_layers(inputs)

    timeline = Timeline(inputs, fps, sr, res, args.background, vclips, aclips, chunks)

    w, h = res
    _vars: dict[str, int] = {
        "width": w,
        "height": h,
        "start": 0,
        "end": timeline.end,
    }

    pool: list[Visual] = []
    for key, obj_str in args.pool:
        if key == "add_text":
            pool.append(
                parse_dataclass(obj_str, TextObj, text_builder, log, _vars, True)
            )
        if key == "add_rectangle":
            pool.append(
                parse_dataclass(obj_str, RectangleObj, rect_builder, log, _vars, True)
            )
        if key == "add_ellipse":
            pool.append(
                parse_dataclass(obj_str, EllipseObj, ellipse_builder, log, _vars, True)
            )
        if key == "add_image":
            pool.append(
                parse_dataclass(obj_str, ImageObj, img_builder, log, _vars, True)
            )

    for obj in pool:
        # Higher layers are visually on top
        # TODO: Use less layers.
        timeline.v.append([obj])

    return timeline
