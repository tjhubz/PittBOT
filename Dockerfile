# use a node base image
FROM python

RUN git clone https://github.com/tjhubz/PittBOT
WORKDIR /PittBOT

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "bot.py" ]
