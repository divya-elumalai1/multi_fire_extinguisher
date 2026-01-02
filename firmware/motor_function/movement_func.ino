
void forward() {
  motor1.setSpeed(speed);   // speed (0–255)
  motor1.run(FORWARD);    // clockwise

  motor2.setSpeed(speed);   // speed (0–255)
  motor2.run(FORWARD);    // clockwise

  motor3.setSpeed(speed);   // speed (0–255)
  motor3.run(FORWARD);    // clockwise

  motor4.setSpeed(speed);   // speed (0–255)
  motor4.run(FORWARD);    // clockwise


}

void backward(){
  motor1.setSpeed(speed);
  motor1.run(BACKWARD); 
  
  motor2.setSpeed(speed);
  motor2.run(BACKWARD); 
  
  motor3.setSpeed(speed);
  motor3.run(BACKWARD); 
  
  motor4.setSpeed(speed);
  motor4.run(BACKWARD);   
}

void right(){
  motor1.setSpeed(speed);
  motor1.run(BACKWARD); 
  
  motor2.setSpeed(speed);
  motor2.run(FORWARD); 
  
  motor3.setSpeed(speed);
  motor3.run(FORWARD); 
  
  motor4.setSpeed(speed);
  motor4.run(BACKWARD);   
}

void left(){
  motor1.setSpeed(speed);
  motor1.run(FORWARD); 
  
  motor2.setSpeed(speed);
  motor2.run(BACKWARD); 
  
  motor3.setSpeed(speed);
  motor3.run(BACKWARD); 
  
  motor4.setSpeed(speed);
  motor4.run(FORWARD);   
}


void stop(){
  motor1.run(RELEASE);

  motor2.run(RELEASE);

  motor3.run(RELEASE);

  motor4.run(RELEASE);
}
