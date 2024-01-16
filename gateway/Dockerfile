FROM python:3.9-alpine
WORKDIR /src
ADD . /src
RUN pip install -r requirements.txt
CMD ["python", "-u", "app.py"]