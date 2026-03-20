FROM node:24

# Build args for Vite env vars
ARG GOOGLE_CLIENT_ID
ARG AUTHENTIK_URL
ARG AUTHENTIK_CLIENT_ID

ENV GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
ENV AUTHENTIK_URL=${AUTHENTIK_URL}
ENV AUTHENTIK_CLIENT_ID=${AUTHENTIK_CLIENT_ID}

WORKDIR /app

# Copy all files to the container
COPY . .

# Install dependencies
RUN npm install

RUN npm run build

# Expose the port the app runs on
#EXPOSE 3000

# Start the application
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]