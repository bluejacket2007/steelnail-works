FROM node:22-alpine

WORKDIR /srv/app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
  CMD wget --spider -q http://localhost:3000/ || exit 1

CMD ["npm", "run", "start"]
