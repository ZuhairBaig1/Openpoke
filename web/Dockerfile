FROM node:alpine3.22

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm install 

COPY . . 

CMD ["npm","run","dev"]





