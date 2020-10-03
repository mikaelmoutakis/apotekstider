#!/usr/bin/env sh
./skrapa \
--config='.secrets' \
--output='../output' \
--cache='../cache' \
--export-cache='../exported_pages' \
--suppress-errors \
--exec='./misc/send_output_files_with_email.py --export-cache={} {}' \
ALLA

