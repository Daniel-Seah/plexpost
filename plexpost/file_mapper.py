import os
import re


def is_video(filename):
    return parse_extension(filename) in ['avi', 'mkv', 'mp4']


def is_subtitle(filename):
    return parse_extension(filename) in ['sub', 'idx', 'srt', 'smi', 'ssa', 'ass', 'vtt']


def parse_extension(filename):
    return os.path.splitext(filename)[1][1:]


def forward_main_videos(torrent):
    videos = [file for file in torrent.files().values() if is_video(file['name'])]
    videos_by_size = sorted(videos, key=lambda v: v['size'], reverse=True)
    if len(videos_by_size) > 0:
        main_video = videos_by_size[0]
        main_filename = main_video['name']
        return [{'download_dir': torrent.downloadDir, 'filename': main_filename, 'dest': main_filename}]
    else:
        return []


def forward_subtitles(torrent):
    mappings = []
    for file in torrent.files().values():
        filename = file['name']
        if is_subtitle(filename):
            rule = {'download_dir': torrent.downloadDir, 'filename': filename, 'dest': filename}
            mappings.append(rule)
    return mappings


def sidecar_subtitle(main_video, subtitles):
    if len(main_video) <= 0:
        return []
    video_dir = os.path.dirname(main_video[0]['filename'])
    if has_sidecar(subtitles, video_dir):
        return []
    elif has_vobsub(subtitles):
        return sidecar_vobsub(subtitles, video_dir)
    else:
        return sidecar_best_non_vobsub(subtitles, video_dir)


def has_sidecar(subtitles, video_dir):
    for sub in subtitles:
        if os.path.dirname(sub['filename']) == video_dir:
            return True
    return False


def sidecar_best_non_vobsub(subtitles, video_dir):
    subs = list(subtitles)
    for sub in subs:
        sub['rank'] = rank_subtitle(sub)
    ranked_subs = sorted(subs, key=lambda s: s['rank'], reverse=True)
    if len(ranked_subs) <= 0:
        return []
    best_sub = ranked_subs[0]
    filename = best_sub['filename']
    basename = os.path.basename(filename)
    rule = {'download_dir': best_sub['download_dir'],
            'filename': filename,
            'dest': video_dir + '/' + basename}
    return [rule]


def rank_subtitle(subtitle):
    name = os.path.basename(subtitle['filename'])
    if is_english_subtitle(name):
        if is_sdh_subtitle(name):
            return 90
        else:
            return 100
    else:
        return 80


def is_english_subtitle(name):
    return contains_any_word_ignoring_case(name, ['english', 'eng', 'en'])


def is_sdh_subtitle(name):
    return contains_any_word_ignoring_case(name, ['sdh'])


def contains_any_word_ignoring_case(line, words):
    pattern = re.compile(r'\b(' + '|'.join(words) + r')\b', re.IGNORECASE)
    return pattern.match(line) is not None


def has_vobsub(subtitles):
    has_idx = False
    has_sub = False
    for sub in subtitles:
        ext = os.path.splitext(sub['filename'])[1][1:]
        if ext == 'idx':
            has_idx = True
        if ext == 'sub':
            has_sub = True
    return has_idx and has_sub


def sidecar_vobsub(subtitles, video_dir):
    mappings = []
    for sub in subtitles:
        filename = sub['filename']
        ext = os.path.splitext(filename)[1][1:]
        basename = os.path.basename(filename)
        if ext in ['idx', 'sub']:
            rule = {'download_dir': sub['download_dir'],
                    'filename': filename,
                    'dest': video_dir + '/' + basename}
            mappings.append(rule)
    return mappings


def move_to_dir(folder, files):
    mappings = []
    for f in files:
        rule = {'download_dir': f['download_dir'], 'filename': f['filename'], 'dest': folder + f['dest']}
        mappings.append(rule)
    return mappings


def map_single_video_download_with_subs(torrent, dest_dir):
    main_video = forward_main_videos(torrent)
    subtitles = forward_subtitles(torrent)
    sidecar_subs = sidecar_subtitle(main_video, subtitles)
    files = main_video + subtitles + sidecar_subs
    return move_to_dir(dest_dir, files)
