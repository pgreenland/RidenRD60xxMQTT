FROM python:3.14-alpine

# Create app directory
RUN mkdir /app

# Use it as the working directory
WORKDIR /app

# Add all local python files and requirements.txt
ADD *.py .
ADD requirements.txt .
ADD config_example.ini .

# Update pip and install requirements
RUN python3 -m pip install --upgrade pip && python3 -m pip install -r requirements.txt

# Launch service
CMD ["python3", "main.py"]
