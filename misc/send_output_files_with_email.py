#!/usr/bin/env python3
"""
USAGE:
    ./misc/send_output_files_with_email.py <directory>
    ./misc/send_output_files_with_email.py -h|--help

OPTIONS:
    -h,--help      Help

DESCRIPTION:
    Sends the xlsx files in output <directory> to the email adresses listed in the .secrets file.
    The 'error.log' file in <directory> is appended to the message body.

CONFIGURATION:
    Append the following text to the '.secrets' config file.

        [email]
        username = <sender_email>
        password = <email password>
        smtp = <smtp url, eg smtp.gmail.com>
        port = 587
        from = <sender_email>
        recipients = <recipient1>,<recipient2>,...
        subject = <subject line text>
        message = <message body>

    Replace placeholder text like <x> with the correct information.
"""

# send path/to/output/folder
# loop over items in folder

# email
import smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formatdate
from email import encoders

# configs
import configparser
import sys
from docopt import docopt


def send_mail(
    send_from,
    send_to,
    subject,
    message,
    files=[],
    server="localhost",
    port=587,
    username="",
    password="",
    use_tls=True,
):
    """Compose and send email with provided info and attachments.

    Args:
        send_from (str): from name
        send_to (list[str]): to name(s)
        subject (str): message title
        message (str): message body
        files (list[str]): list of file paths to be attached to email
        server (str): mail server host name
        port (int): port number
        username (str): server auth username
        password (str): server auth password
        use_tls (bool): use TLS mode

    Adapted from https://stackoverflow.com/questions/3362600/how-to-send-email-attachments
    """
    msg = MIMEMultipart()
    msg["From"] = send_from
    msg["To"] = ",".join(send_to)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    msg.attach(MIMEText(message))

    for path in files:
        part = MIMEBase("application", "octet-stream")
        with open(path, "rb") as file:
            part.set_payload(file.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", 'attachment; filename="{}"'.format(Path(path).name)
        )
        msg.attach(part)

    smtp = smtplib.SMTP(server, port)
    if use_tls:
        smtp.starttls()
    smtp.login(username, password)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.quit()


if __name__ == "__main__":
    arguments = docopt(__doc__)
    secrets = configparser.ConfigParser()
    secrets.read(".secrets")
    conf = secrets["email"]
    folder_to_send = Path(arguments["<directory>"])
    if not folder_to_send.is_dir():
        raise FileNotFoundError(f"{folder_to_send} is not a valid directory")
    else:
        with Path.joinpath(folder_to_send, "error.log") as el:
            errors_text = el.read_text()
        divider_text = "\n" * 2 + "#" * 40 + "\n" + "Errors:" + "\n" + "#" * 40 + "\n"
        message_text = conf["message"] + divider_text + errors_text
        send_to = conf["recipients"].split(",")
        send_mail(
            send_from=conf["from"],
            send_to=send_to,
            subject=conf["subject"],
            message=message_text,
            files=folder_to_send.glob("*.xlsx"),
            server=conf["smtp"],
            port=int(conf["port"]),
            username=conf["username"],
            password=conf["password"],
        )
