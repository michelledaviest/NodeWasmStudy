# docker context ls
# docker context use default

# To run this Dockerfile 
# sudo docker build -t dywasmbench . && sudo docker run -it dywasmbench 

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

# Install ghtopdep for dataset collection 
RUN pip install ghtopdep
RUN pip install bs4
RUN pip install matplotlib

# Install dependencies for repo: hazae41/berith
RUN curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="/root/.deno/bin:${PATH}" 

RUN mkdir -p /home/NoWaSet/
RUN mkdir -p /home/NoWaSet/repos/
RUN mkdir -p /home/NoWaSet/scripts/

COPY node-wasm-set.json /home/NoWaSet/scripts/
COPY utils.py /home/NoWaSet/scripts/

RUN python3 /home/NoWaSet/scripts/utils.py --clone-build-all

WORKDIR /home/NoWaSet