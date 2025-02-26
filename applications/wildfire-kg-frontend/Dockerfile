FROM node:18-alpine

ARG NODE_ENV=development
ENV NODE_ENV=$NODE_ENV

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

RUN if [ "$NODE_ENV" = "production" ]; then \
        npm run build; \
    fi

CMD if [ "$NODE_ENV" = "production" ]; then \
        npm run start; \
    else \
        npm run dev; \
    fi 