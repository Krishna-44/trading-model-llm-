FROM node:20-alpine

WORKDIR /app
ARG NEXT_PUBLIC_AIFOS_API=http://localhost:8000
ENV NEXT_PUBLIC_AIFOS_API=$NEXT_PUBLIC_AIFOS_API

COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
