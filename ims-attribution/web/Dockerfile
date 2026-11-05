FROM nginx:alpine

# Copy frontend files
COPY web/index.html /usr/share/nginx/html/index.html
COPY web/pixel.js /usr/share/nginx/html/pixel.js

# Copy custom Nginx reverse proxy configuration
COPY web/nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
