FROM python:3.9-alpine
WORKDIR /src
ADD . /src
RUN pip install -r requirements.txt
EXPOSE 8081
CMD ["python", "-u", "app.py"]