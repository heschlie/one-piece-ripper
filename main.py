#!/usr/bin/env python

import json
import math
import os
from pathlib import Path
import subprocess
import logging
import sys

import ffmpeg
from makemkv import MakeMKV, ProgressParser, MakeMKVError
from tvdb_v4_official import TVDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get('API_KEY')
API_PIN = os.environ.get('API_PIN')

j = '''[
  "--ui-language",
  "en_US",
  "--output",
  "{output}",
  "--language",
  "0:en",
  "--display-dimensions",
  "0:{display_dimensions}",
  "--language",
  "1:en",
  "--track-name",
  "1:Surround 5.1",
  "--language",
  "2:ja",
  "--track-name",
  "2:Stereo",
  "--language",
  "3:en",
  "--language",
  "4:en",
  "(",
  "{input}",
  ")",
  "--split",
  "chapters:{chapters}",
  "--track-order",
  "0:0,0:1,0:2,0:3,0:4"
]
'''


def main():
    base_dir, start_number = parse_args()
    mkv_fname, chapter_markers, disc_name, drive = rip_disc(base_dir)
    episodes = split_episodes(mkv_fname, chapter_markers)
    rename_episodes(base_dir, disc_name, episodes, start_number)
    os.system(f'umount {drive}')
    os.system(f'eject {drive}')


def parse_args() -> tuple[Path, int]:
    if len(sys.argv) != 3:
        logger.error('Usage: one-piece-ripper.py output_directory starting_episode_number')
        exit(1)
    base_dir = Path(sys.argv[1]).absolute()
    starting_episode_number = int(sys.argv[2])
    return base_dir, starting_episode_number


def rip_disc(base_dir: Path) -> tuple[str, list[int], str, str]:
    """
    Rips the disc using MakeMKV. It tries to find the largest title on the DVD then proceeds
    to gather some information about it before ripping it to disk as an MKV. This MKV
    contains all episodes on the disc, sorted by chapters, and contains the data on how the
    episodes are divided into chapters which we also return. Finally, just some metadata on
    the name of the disc, and where it was mounted.

    :param base_dir: Base directory to store files
    :return: MKV filename, Episode divisions by chapters, Name of disc, Where disc is mounted
    """
    with ProgressParser() as progress:
        mkv = MakeMKV(0, progress_handler=progress.parse_progress)
        logger.info('Reading info from disc')
        info = mkv.info()
        disc_name = info['disc']['name']
        output_dir = Path(f'{base_dir}/{disc_name}')
        drive = info['drives'][0]['device_path']
        title = find_largest_title(info['titles'])
        chapter_markers = find_segments(info['titles'][title])
        output_dir.mkdir(exist_ok=True)
        try:
            logger.info('Ripping disc, this may take some time')
            mkv.mkv(title, str(output_dir))
        except MakeMKVError as e:
            logger.error(f'Failed to rip title from disc: {e}')
            exit(1)
        title_fname = info['titles'][title]['file_output']
        mkv_fname = f'{output_dir}/{title_fname}'

    return mkv_fname, chapter_markers, disc_name, drive


def find_segments(title) -> list[int]:
    """
    Take the segments metadata from the DVD and returns the chapters we need for splitting
    the MKV up into the actual episodes.

    :param title: Title metadata
    :return: list of chapters to split on
    """
    segments = []
    for s in title['segments_map'].split(','):
        if '-' in s:
            segments.append(int(s.split('-')[0]))
        else:
            segments.append(int(s))

    # Remove value 1 from list, as we want to split AFTER the first episode not before
    try:
        segments.remove(1)
    except ValueError:
        logger.debug('Did not find a segment with "1"')

    return segments


def find_largest_title(titles: list) -> int:
    """
    Finds the larges `Title` on the disc, this contains all our episodes

    :param titles: Title metadata
    :return: Title number with the episodes
    """
    logger.info('Finding largest title')
    largest = {'title': 0, 'size': 0}
    for i, title in enumerate(titles):
        size = title['size']
        if size > largest['size']:
            largest['size'] = size
            largest['title'] = i

    logger.info(f'Found {largest["title"]} with size {titles[largest["title"]]["size_human"]}')
    return largest['title']


def split_episodes(mkv_fname: str, chapter_markers: list[int]) -> list[str]:
    """
    Splits up the episodes based on the given chapter markers using `mkvmerge`. We skip generating
    the command and just use json input. This is mainly because I'm too lazy to try and properly
    figure out how to build the command, and this json was pulled from MKVToolNix then templated
    to work, this is likely brittle.

    :param mkv_fname: Filename of the MKV to split
    :param chapter_markers: What chapters to split it on
    :return: A list of filenames we just created
    """
    logger.info(f'Splitting {mkv_fname} into episodes')
    ppath = str(Path(mkv_fname).parent) + '/'
    json_path = ppath + 'mkvmerge.json'
    output = ppath + 'episode.mkv'

    probe = ffmpeg.probe(mkv_fname, show_chapters=None)
    display_dimensions = probe['streams'][0]['display_aspect_ratio'].replace(':', 'x')
    if len(chapter_markers) == 0:
        chapter_markers = find_credits(probe['chapters'])
    chapter_string = ','.join(map(str, chapter_markers))

    payload = json.loads(j.format(output=output, input=mkv_fname, chapters=chapter_string,
                                  display_dimensions=display_dimensions))
    with open(json_path, 'w') as f:
        json.dump(payload, f, indent=4)

    subprocess.run(['mkvmerge', f'@{json_path}'], check=True, capture_output=True)
    try:
        os.remove(ppath + 'episode-{:>03}.mkv'.format(len(chapter_markers) + 1))
    except FileNotFoundError:
        logger.info("No trailing clip to remove")

    os.remove(mkv_fname)
    os.remove(json_path)

    files = []
    for i in range(1, len(chapter_markers)+1):
        files.append(f'episode-{i:>03}.mkv')
    return files


def find_credits(chapters: dict) -> list[int]:
    """
    Alternative way to locate episode breaks if chapter metadata is not present. We simply look for
    chapters that are ~30s long.

    :param chapters: Chapter metadata
    :return: List of chapters to split on
    """
    episode_markers = []
    for i, chapter in enumerate(chapters):
        d = math.floor((chapter['end'] - chapter['start']) / 1000000000)
        if 28 < d < 32:
            end = i+2
            logger.info(f'Found end credits -- {chapter["tags"]["title"]} - {d}s')
            episode_markers.append(end)

    logger.info(f'Found {len(episode_markers)} episodes')
    return episode_markers


def rename_episodes(directory: Path, disc_name: str, episodes: list[str], starting_episode: int):
    """
    Remanes and moves the episodes into their season directory. Using the start episode from
    the CLI arguments, we find that episode on TVDB using absolute (this number is on the physical
    disc and case) then we take that ID and look it up using the air date listings which Plex
    is happier with. We then put it into the format "$show - S$seasonE$episode - $title"

    This method cleans up everything when finished, not ideal, but it is convenient

    :param directory: Base directory for files
    :param disc_name: Name of the disc so we can find the subdir
    :param episodes: List of episode names to be renamed
    :param starting_episode: What is the first episode on the disc in absolute episode numbering
    """
    start = starting_episode-1
    end = start+len(episodes)
    tvdb = TVDB(API_KEY, API_PIN)
    all_episodes_abs = fetch_all_episodes(tvdb, 'absolute')
    all_episodes = fetch_all_episodes(tvdb)
    eps_abs = all_episodes_abs[start:end]
    disc_dir = Path(f'{directory}/{disc_name}')

    # Translate the absolute numbers to "seasons" to make Plex happy
    my_eps = []
    for e in eps_abs:
        my_eps.append(list(filter(lambda ep: ep['id'] == e['id'], all_episodes))[0])

    for i, e in enumerate(episodes):
        episode = my_eps[i]
        season = episode['seasonNumber']
        episode_number = episode['number']
        title = episode['name']
        season_dir = Path(f'{directory}/Season {season}')
        fname = f'One Piece - S{season:>02}E{episode_number:>02} - {title}.mkv'

        src = f'{disc_dir}/{e}'
        dst = f'{season_dir}/{fname}'
        season_dir.mkdir(exist_ok=True)
        logger.info(f'Renaming {src} to {dst}')
        os.rename(src, dst)

    os.rmdir(disc_dir)


def fetch_all_episodes(tvdb: TVDB, season_type='default') -> list[dict]:
    """
    Fetches all episodes from TVDB, we need to vary the `season_type` so it is here to allow that.

    :param tvdb: TVDB object to pull API data from
    :param season_type: default, absolute, dvd
    :return: A list of all episode metadata
    """
    episodes = []
    for i in range(0, 100):
        one_piece_page = tvdb.get_series_episodes(81797, lang='eng', season_type=season_type, page=i)
        if len(one_piece_page['episodes']) == 0:
            return episodes
        episodes.extend(one_piece_page['episodes'])


if __name__ == '__main__':
    main()
