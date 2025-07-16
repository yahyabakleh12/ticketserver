CREATE TABLE User (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE Ticket (
    id INT AUTO_INCREMENT PRIMARY KEY,
    token VARCHAR(255) NOT NULL UNIQUE,
    access_point_id INT,
    number VARCHAR(50),
    code VARCHAR(50),
    city VARCHAR(100),
    status VARCHAR(50),
    entry_time DATETIME,
    exit_time DATETIME,
    entry_pic_base64 LONGTEXT,
    car_pic LONGTEXT, -- to store base64 image
    exit_video_path VARCHAR(255),
    spot_number INT,
    trip_p_id INT,
    ticket_key_id INT
);
