#!/usr/bin/env sh
cd ~/apotekstider
./skrapa \
--profile=../firefox-profile \
--headless \
--supress-errors \
--exec='./misc/send_output_files_with_email.py {}' && \
echo 'Finished!'


