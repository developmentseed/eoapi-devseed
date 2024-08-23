CREATE USER business WITH PASSWORD 'casual';
CREATE SCHEMA business AUTHORIZATION business;
GRANT ALL PRIVILEGES ON SCHEMA business TO business;
ALTER ROLE business SET search_path TO business, public;
