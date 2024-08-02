#!/bin/bash 

mkdir -p docker-tmp
sudo docker build -t realwasm .
sudo docker run -it \
    --mount type=bind,source="/data/RealWasm/data",target=/home/RealWasm/data \
    --mount type=bind,source="/data/RealWasm/scripts",target=/home/RealWasm/scripts \
    --mount type=bind,source="/data/RealWasm/docker-tmp",target=/home/RealWasm/docker-tmp \
    realwasm