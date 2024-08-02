# docker context ls
# docker context use default

# To run this Dockerfile 
# sudo docker build -t realwasm .
# sudo docker run -it \
#     --mount type=bind,source="/data/RealWasm/data",target=/home/RealWasm/data \
#     --mount type=bind,source="/data/RealWasm/scripts",target=/home/RealWasm/scripts \
#     --mount type=bind,source="/data/RealWasm/docker-tmp",target=/home/RealWasm/docker-tmp \
#     realwasm

FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive

SHELL ["/bin/bash", "-c"]

RUN apt-get update \ 
   && apt-get -y install sudo build-essential curl wget git unzip \ 
   && apt install -y python3 pip vim 

# Install nvm with node and npm
ENV NVM_DIR /usr/local/nvm
RUN mkdir -p $NVM_DIR
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh | bash
ENV NODE_VERSION v21.6.1
RUN /bin/bash -c "source $NVM_DIR/nvm.sh && nvm install $NODE_VERSION && nvm use --delete-prefix $NODE_VERSION"

ENV NODE_PATH $NVM_DIR/versions/node/$NODE_VERSION/lib/node_modules
ENV PATH      $NVM_DIR/versions/node/$NODE_VERSION/bin:$PATH

RUN npm install --global yarn turbo pnpm 

# Install Rust and wasm-tools 
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}" 
RUN cargo install wasm-tools 

# Install prettytable for nice tables 
RUN pip install prettytable

# Install ghtopdep for the collect-dataset.py script 
RUN pip install ghtopdep
RUN pip install bs4

# Install dependencies for dependency-analysis.py script 
RUN pip install matplotlib

# Instead of making a metadata dir in the guest, make it on the host and mount it:
# mkdir -p /path/to/RealWasm/metadata
# docker ... --mount type=bind,source="/path/to/RealWasm/metadata",target=/home/RealWasm/metadata ...

RUN mkdir -p /home/RealWasm/

# # Copy over different scripts 
# RUN mkdir -p /home/RealWasm/scripts
# COPY ./scripts/utils.py /home/RealWasm/scripts
# COPY ./scripts/collect-dataset.py /home/RealWasm/scripts
# COPY ./scripts/dependency-analysis.py /home/RealWasm/scripts
# COPY ./scripts/get-wasm-static-info.py /home/RealWasm/scripts
# COPY ./scripts/collect-dynamic-results.py /home/RealWasm/scripts
# COPY ./scripts/get-paper-results.py /home/RealWasm/scripts
# COPY ./scripts/node-no-expose-wasm /home/RealWasm/scripts/node-no-expose-wasm
# COPY ./scripts/get-wasm-source /home/RealWasm/scripts/get-wasm-source

# Clone npm-filter 
RUN mkdir -p /home/RealWasm/tools 
WORKDIR /home/RealWasm/tools 
RUN git clone https://github.com/emarteca/npm-filter.git
# Install dependencies of npm_filter 
RUN pip install xmltodict setuptools setuptools_rust wheel pandas

# Install dependencies for repo: hazae41/berith
RUN curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="/root/.deno/bin:${PATH}" 

RUN export DENO_INSTALL="/root/.deno"
RUN export PATH="$DENO_INSTALL/bin:$PATH"

# Install packages for get-wasm-sources
#WORKDIR /home/RealWasm/scripts/get-wasm-source
#RUN npm install 

WORKDIR /home/RealWasm/scripts
#CMD python3 ./collect-dynamic-results.py --output-dir ./../data