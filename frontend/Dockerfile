# Use Node.js image for build
FROM node:18-alpine as build

WORKDIR /app

COPY ./frontend/package*.json ./
RUN npm install

COPY ./frontend /app

RUN npm run build

# Use nginx to serve the build files
FROM nginx:alpine

COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
