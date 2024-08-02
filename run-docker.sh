#!/bin/bash 

mkdir -p docker-tmp
sudo docker build -t realwasm .
sudo docker run -it \
    --mount type=bind,source="./data/",target=/home/RealWasm/data \
    --mount type=bind,source="./scripts",target=/home/RealWasm/scripts \
    --mount type=bind,source="./docker-tmp",target=/home/RealWasm/docker-tmp \
    realwasm