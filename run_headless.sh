#!/usr/bin/env sh
cd ~/apotekstider
./skrapa \
--profile='../firefox-profile' \
--output='../output' \
--cache='../cache' \
--export-cache='../exported_pages' \
--headless \
--suppress-errors \
--exec='./misc/send_output_files_with_email.py --export-cache={} {}' \
ALLA
killall firefox
