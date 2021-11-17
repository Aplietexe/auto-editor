'''utils/video.py'''

# Internal Libraries
import os.path

# Included Libraries
from .func import fnone

def fset(cmd, option, value):
    if(fnone(value)):
        return cmd
    return cmd + [option] + [value]


def mux_quality_media(ffmpeg, spedup, rules, write_file, container, args, inp, temp, log):
    s_tracks = 0 if not rules['allow_subtitle'] else len(inp.subtitle_streams)
    a_tracks = 0 if not rules['allow_audio'] else len(inp.audio_streams)
    v_tracks = 0 if not rules['allow_video'] else len(inp.video_streams)

    cmd = []
    if(spedup is not None):
        cmd.extend(['-i', spedup])

    if(a_tracks > 0):
        if(args.keep_tracks_seperate and rules['max_audio_streams'] == 1):
            log.warning(
                "'{}' container doesn't support multiple audio tracks.".format(container)
            )

        if(args.keep_tracks_seperate and rules['max_audio_streams'] is None):
            for t in range(a_tracks):
                cmd.extend(['-i', os.path.join(temp, 'new{}.wav'.format(t))])
        else:
            # Merge all the audio a_tracks into one.
            new_a_file = os.path.join(temp, 'new_audio.wav')
            if(a_tracks > 1):
                new_cmd = []
                for t in range(a_tracks):
                    new_cmd.extend(['-i', os.path.join(temp, 'new{}.wav'.format(t))])
                new_cmd.extend(['-filter_complex', 'amerge=inputs={}'.format(a_tracks),
                    '-ac', '2', new_a_file])
                ffmpeg.run(new_cmd)
            else:
                new_a_file = os.path.join(temp, 'new0.wav')
            cmd.extend(['-i', new_a_file])

    if(s_tracks > 0):
        for s, sub in enumerate(inp.subtitle_streams):
            new_path = os.path.join(temp, 'new{}s.{}'.format(s, sub['ext']))
            cmd.extend(['-i', new_path])

    total_streams = v_tracks + s_tracks + (a_tracks if args.keep_tracks_seperate else min(a_tracks, 1))

    for i in range(total_streams):
        cmd.extend(['-map', '{}:0'.format(i)])

    if(v_tracks > 0):
        cmd = fset(cmd, '-crf', args.constant_rate_factor)
        cmd = fset(cmd, '-b:v', args.video_bitrate)
        cmd = fset(cmd, '-tune', args.tune)
        cmd = fset(cmd, '-preset', args.preset)

        cmd.extend(['-movflags', '+faststart'])

        if(fnone(args.video_codec)):
            if(rules['vcodecs'] is None):
                cmd.extend(['-c:v', 'copy'])
            else:
                cmd.extend(['-c:v', rules['vcodecs'][0]])
        else:
            vcodec = args.video_codec
            if(vcodec == 'copy'):
                vcodec = inp.video_streams[0].codec
            if(vcodec == 'uncompressed'):
                vcodec = 'copy'

            # Rules checking is in edit.py
            cmd.extend(['-c:v', vcodec])

    if(s_tracks > 0):
        codec = inp.subtitle_streams[0]['codec']
        cmd.extend(['-c:s', codec])

    if(a_tracks > 0):
        cmd = fset(cmd, '-c:a', args.audio_codec)
        cmd = fset(cmd, '-b:a', args.audio_bitrate)

        if(fnone(args.sample_rate)):
            if(rules['samplerate'] is not None):
                cmd.extend(['-ar', str(rules['samplerate'][0])])
        else:
            cmd.extend(['-ar', str(args.sample_rate)])

    cmd.extend(['-strict', '-2', write_file]) # Allow experimental codecs.
    ffmpeg.run(cmd)
