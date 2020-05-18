#!/usr/bin/python3

from pythonopensubtitles.opensubtitles import OpenSubtitles
import sys
import json
import zlib
import base64
import os
import errno
import shutil
import pysubs2
import re
import argparse
import time
import datetime

import pprint

pp = pprint.PrettyPrinter(indent=4)

parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument(
    "--videolist-file",
    required=True,
    help="a file containing one path to a video file on each line (program input)",
)
parser.add_argument(
    "--database-dir",
    required=True,
    help="directory for generated database files (program output), merges data if file already exists",
)
parser.add_argument(
    "--clean-existing-database",
    action="store_true",
    help="do not merge new data into existing file; replace file instead",
)
parser.add_argument(
    "--dry-run", action="store_true", help="do not modify database.json"
)

args = parser.parse_args()

videolist_file_path = args.videolist_file
database_dir = args.database_dir
clean_existing_database = args.clean_existing_database
dry_run = args.dry_run
database_path = os.path.join(database_dir, "database.json")

print(videolist_file_path)

with open(videolist_file_path) as f:
    video_paths = [line.strip() for line in f]
    video_paths = [x for x in video_paths if x]


def make_parents(filename):
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise


def decompress(data, encoding):
    """
    Convert a base64-compressed subtitles file back to a string.

    :param data: the compressed data
    :param encoding: the encoding of the original file (e.g. utf-8, latin1)
    """
    try:
        return zlib.decompress(base64.b64decode(data), 16 + zlib.MAX_WBITS).decode(
            encoding
        )
    except UnicodeDecodeError as e:
        print(e, file=sys.stderr)
        return


def download_subtitles(
    ost,
    ids,
    encoding,
    override_filenames=None,
    output_directory=".",
    override_directories=None,
    extension="srt",
    return_decoded_data=False,
):
    override_filenames = override_filenames or {}
    override_directories = override_directories or {}
    successful = {}

    # OpenSubtitles will accept a maximum of 20 IDs for download
    if len(ids) > 20:
        print("Cannot download more than 20 files at once.", file=sys.stderr)
        ids = ids[:20]

    response = ost.xmlrpc.DownloadSubtitles(ost.token, ids)
    status = response.get("status").split()[0]
    encoded_data = response.get("data") if "200" == status else None

    if not encoded_data:
        return None

    for item in encoded_data:
        subfile_id = item["idsubtitlefile"]

        decoded_data = decompress(item["data"], encoding)

        if not decoded_data:
            print(
                "An error occurred while decoding subtitle "
                "file ID {}.".format(subfile_id),
                file=sys.stderr,
            )
        elif return_decoded_data:
            successful[subfile_id] = decoded_data
        else:
            fname = override_filenames.get(subfile_id, subfile_id + "." + extension)
            directory = override_directories.get(subfile_id, output_directory)
            fpath = os.path.join(directory, fname)
            make_parents(fpath)

            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(decoded_data)
                successful[subfile_id] = fpath
            except IOError as e:
                print(
                    "There was an error writing file {}.".format(fpath), file=sys.stderr
                )
                print(e, file=sys.stderr)

    return successful or None


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    exit_cmd = ["q", "Q", "Quit", "quit", "exit"]
    if default is None:
        prompt = " [y/n/q] "
    elif default == "yes":
        prompt = " [Y/n/q] "
    elif default == "no":
        prompt = " [y/N/q] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        choice = input(question + prompt).lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in exit_cmd:
            sys.exit(0)
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


def handle_subtitle(opensubtitles_metadata):
    # find subtitle ending (srt, ass, ...)
    # if subtitle['SubFormat'] not in sub_format_to_ending:
    #    sub_info_json = json.dumps(subtitle, indent=4)
    #    print(sub_info_json)
    #    print('Unreckognized subtitle format \'%s\'! Skipping this subtitle!' % subtitle['SubFormat'])
    #    continue
    # sub_ending = sub_format_to_ending[sub_format_to_ending[subtitle['SubFormat']]]

    # sub_filename = '{}-{:0>04}.{}'.format(movie_name_normalized, subtitle_idx, sub_ending)
    # sub_data_filename = '{}-{:0>04}.{}'.format(movie_name_normalized, subtitle_idx, 'json')
    sub_id = opensubtitles_metadata["IDSubtitleFile"]
    print("Downloading subtitle with id `%s`..." % sub_id, file=sys.stderr, end=" ")
    data = None
    try:
        time.sleep(0.4)
        data = download_subtitles(
            ost,
            [sub_id],
            opensubtitles_metadata["SubEncoding"],
            return_decoded_data=True,
        )
    except KeyboardInterrupt:
        raise 
    except:
        print("error occured")

    if data == None:
        print("Error getting data - skipping subtitle!", file=sys.stderr)
        return None

    print("Done!", file=sys.stderr)

    ssa_styling_pattern = re.compile(r"\s*#?{[^}]*}#?\s*")  # remove SSA-styling info
    newline_whitespace = re.compile(
        r"\s*\n\s*"
    )  # remove unnecessary trailing space around newlines

    line_data = []

    decoded_sub_data = pysubs2.SSAFile.from_string(
        data[sub_id], encoding=opensubtitles_metadata["SubEncoding"]
    )
    for line in decoded_sub_data:
        if "www.opensubtitles.org" in line.text.lower():
            continue  # remove ad as this throws of pairing/statistics (same text in different places)

        text = line.text.replace("\n", "").replace("\r", "")
        text = ssa_styling_pattern.sub("", text)
        text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)
        text = text.replace(r"\N", "\n")
        text = text.strip()
        text = newline_whitespace.sub("\n", text)

        if line.start < line.end:
            line_data.append({"start_ms": line.start, "end_ms": line.end, "text": text})
        elif line.start > line.end:
            line_data.append({"start_ms": line.end, "end_ms": line.start, "text": text})
        else:
            # start == end
            pass

    line_data = sorted(line_data, key=lambda l: l["start_ms"])

    return {
        "id": opensubtitles_metadata["IDSubtitleFile"],
        "opensubtitles_metadata": opensubtitles_metadata,
        "data": line_data,
    }


def handle_subtitle_files(
    movie_id, reference_subtitle_metadata, opensubtitle_metadatas
):

    reference_subtitle_entry = handle_subtitle(reference_subtitle_metadata)
    if reference_subtitle_entry == None:
        print("failed to download reference subtitle...", file=sys.stderr)
        return None

    token = ost.login("", "")
    print("New OpenSubtitles token: %s" % token, file=sys.stderr)

    result_subtitles_list = []

    for opensubtitle_metadata in opensubtitle_metadatas:
        if (
            opensubtitle_metadata["IDSubtitle"]
            == reference_subtitle_metadata["IDSubtitle"]
        ):
            print("skipping reference subtitle...", file=sys.stderr)
            continue

        subtitle_entry = handle_subtitle(opensubtitle_metadata)
        if subtitle_entry == None:
            continue
        result_subtitles_list.append(subtitle_entry)

    return (reference_subtitle_entry, result_subtitles_list)


def ask_user_for_movie(movie_name, correct_subtitle_metadata, subtitle_files):

    movie_name_normalized = movie_name.lower().replace(" ", "-")

    data = ost.search_movies_on_imdb(movie_name)
    for film in data["data"]:
        if "from_redis" in film and film["from_redis"] == "false":
            continue
        print("%s [IMDB-ID: %s]" % (film["title"], film["id"]), file=sys.stderr)
        answer = query_yes_no("Download subtitles for this movie?")
        print(file=sys.stderr)
        if answer is True:
            imdb_id = film["id"]
            subtitle_files = ost.search_subtitles(
                [{"imdbid": imdb_id, "sublanguageid": "eng"}]
            )
            handle_subtitle_files(
                movie_name_normalized, correct_subtitle_metadata, subtitle_files
            )

            sys.exit(0)


def to_normalized_name(s):
    printable = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-")
    return "".join(filter(lambda x: x in printable, s.lower().replace(" ", "-")))


ost = OpenSubtitles()
from pythonopensubtitles.utils import File as OstFile

token = ost.login("", "")
print("OpenSubtitles token: %s" % token, file=sys.stderr)


if clean_existing_database:
    movies = {}
else:
    try:
        with open(database_path) as f:
            movies = {movie["id"]: movie for movie in json.load(f)["movies"]}
    except IOError:
        movies = {}

movies_without_reference_sub_count = 0
movies_with_reference_sub_count = 0

all_subtitles = {}
all_ref_subtitles = {}

for file_idx, file_path in enumerate(video_paths):
    f = OstFile(file_path)
    file_hash = f.get_hash()
    file_basename = os.path.basename(file_path)

    print(file=sys.stderr)
    print("-------------------------------------------------------", file=sys.stderr)
    print(
        "[%s/%s] Movie `%s` with hash `%s`:"
        % (file_idx, len(video_paths), file_basename, file_hash),
        file=sys.stderr,
    )

    time.sleep(0.2)
    subtitle_files = ost.search_subtitles(
        [{"moviehash": file_hash, "sublanguageid": "eng", "moviebytesize": f.size}]
    )
    if len(subtitle_files) == 0:
        print("NOT REGISTERED on OpenSubtitles", file=sys.stderr)
        movies_without_reference_sub_count = movies_without_reference_sub_count + 1

        continue

    # pp.pprint([(f['MovieName'],f['Score'],f['IDMovie']) for f in subtitle_files])

    movie_ids = [f["IDMovie"] for f in subtitle_files]
    most_probable_movie = max(set(movie_ids), key=movie_ids.count)
    # if movie_ids.count(most_probable_movie) < 2:
    #    print('UNSURE', file=sys.stderr)
    #    continue

    correct_subtitle_file = next(
        x for x in subtitle_files if x["IDMovie"] == most_probable_movie
    )

    # if correct_subtitle_file['MovieKind'] != 'movie':
    #    print('NOT MOVIE')
    #    continue

    movies_with_reference_sub_count = movies_with_reference_sub_count + 1
    movie_name = correct_subtitle_file["MovieName"]
    movie_name_normalized = to_normalized_name(movie_name)
    movie_id = "%s#%s" % (movie_name_normalized, file_hash)
    print("moviename is `%s`" % movie_name, file=sys.stderr)

    time.sleep(0.2)
    subtitles_metadata = ost.search_subtitles(
        [{"idmovie": correct_subtitle_file["IDMovie"], "sublanguageid": "eng"}]
    )

    try:
        movie_database_entry = movies[movie_id]
        known_subtitles = set(
            [
                subtitles_metadata["id"]
                for subtitles_metadata in movie_database_entry["subtitles"]
            ]
        )
    except KeyError:
        movie_database_entry = {
            "id": movie_id,
            "name": movie_name,
            "path": file_path,
            "reference_subtitle": None,
            "subtitles": [],
        }
        known_subtitles = set()

    all_ref_subtitles[correct_subtitle_file["IDSubtitleFile"]] = {
        "id": correct_subtitle_file["IDSubtitleFile"],
        "movie_id": movie_id,
        "metadata": correct_subtitle_file,
    }

    for subtitle_metadata in subtitles_metadata:
        if (
            subtitle_metadata["IDSubtitleFile"]
            == correct_subtitle_file["IDSubtitleFile"]
        ):
            continue

        all_subtitles[subtitle_metadata["IDSubtitleFile"]] = {
            "id": subtitle_metadata["IDSubtitleFile"],
            "reference_id": correct_subtitle_file["IDSubtitleFile"],
            "movie_id": movie_id,
            "metadata": subtitle_metadata,
        }

    movies[movie_id] = movie_database_entry

#    movies_list.append(
#    reference_subtitle, subtitle_list = handle_subtitle_files(movie_id, correct_subtitle_file, subtitle_metadatas)
#        {
#            "id": movie_id,
#            "name": movie_name,
#            "path": file_path,
#            "reference_subtitle": reference_subtitle,
#            "subtitles": subtitle_list
#        }
#    )


def downloaded_subtitles_id(movies, movie_id):
    return [subtitle["id"] for subtitle in movies[movie_id]["subtitles"]]


max_sub_count_for_movie = 2

subtitles_to_download_ids_for_movie_id = {}
for sub_id, sub_data in all_subtitles.items():
    movie_id = sub_data["movie_id"]
    if sub_id in downloaded_subtitles_id(movies, movie_id):
        continue
    try:
        subtitles_set = subtitles_to_download_ids_for_movie_id[movie_id]
    except KeyError:
        subtitles_set = set()
        subtitles_to_download_ids_for_movie_id[movie_id] = subtitles_set

    if len(subtitles_set) < max_sub_count_for_movie:
        subtitles_set.add(sub_id)

print("---->>")
pp.pprint(subtitles_to_download_ids_for_movie_id)

stop_download = False
try:
    for movie_id, sub_ids in subtitles_to_download_ids_for_movie_id.items():
        if stop_download:
            break

        movie_database_entry = movies[movie_id]
        for sub_id in sub_ids:
            if stop_download:
                break

            download_subtitle_data = all_subtitles[sub_id]
            if movie_database_entry["reference_subtitle"] == None:
                print("%s -> ref %s" % (movie_id, sub_id))
                ref_sub_id = download_subtitle_data["reference_id"]
                try:
                    sd = handle_subtitle(all_ref_subtitles[ref_sub_id]["metadata"])
                    if sd == None:
                        break
                    movie_database_entry["reference_subtitle"] = sd
                except KeyboardInterrupt:
                    print("Interrupted downloading ref sub.")
                    stop_download = True
                    break
                except Exception as e:
                    pp.pprint(all_ref_subtitles[ref_sub_id])
                    print(
                        "Error downloading subtitle '{}' for movie '{}'... Skipping this movie...".format(
                            sub_id, movie_id
                        )
                    )
                    break

            print("%s -> normal %s" % (movie_id, sub_id))
            sd = handle_subtitle(all_subtitles[sub_id]["metadata"])
            if sd == None:
                continue
            movie_database_entry["subtitles"].append(sd)
except KeyboardInterrupt:
    print("Interrupted downloading.")
    pass
except Exception as e:
    print("Unexpected error: %s" % e)
    pass


movies_list = [
    movie_data
    for movie_id, movie_data in movies.items()
    if movie_data["reference_subtitle"] != None
]

# pp.pprint(movies_list)

database_object = {
    "movies": movies_list,
    "movies_without_reference_sub_count": movies_without_reference_sub_count,
    "movies_with_reference_sub_count": movies_with_reference_sub_count,
}


if dry_run:
    print("Not writing database file because of '--dry-run'...", file=sys.stderr)
    print(file=sys.stderr)
else:
    print(file=sys.stderr)
    print("Writing database file...", file=sys.stderr, end="")
    os.makedirs(database_dir, exist_ok=True)

    try:
        timestring = datetime.datetime.now().strftime("%Y-%m-%d--H%H-M%M-S%S")
        database_bk_path = os.path.join(
            database_dir, "database-bk-%s.json" % timestring
        )
        os.rename(database_path, database_bk_path)
    except:
        pass

    with open(database_path, "w") as f:
        json.dump(database_object, f)

print("Done!", file=sys.stderr)

sys.exit(0)
