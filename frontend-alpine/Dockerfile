FROM nginx:1.27-alpine

# Static assets
COPY index.html login.html register.html credits.html chat.html pool.html nodes.html earnings.html agent.html profile.html /usr/share/nginx/html/
COPY pool.js nodes.js earnings.js agent.js profile.js /usr/share/nginx/html/
COPY particles.js /usr/share/nginx/html/
COPY app.js style.css /usr/share/nginx/html/

# Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
