FROM python:3.13.12-alpine3.23

WORKDIR /app/server

COPY requirements.txt ./

RUN pip install -r requirements.txt

COPY . . 

WORKDIR /app

CMD ["python","-m","server.server","--reload"]

