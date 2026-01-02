void motor_test(){
   // Run motor clockwise
  Serial.println("Forward");
  forward();
  delay(4000);           // run for 3 seconds

   // Stop motor
  Serial.println("Stopped");
  stop();
  delay(1000);

  // Run motor anticlockwise
  Serial.println("Backward");
  backward();// anticlockwise
  
  delay(4000);

  // Stop motor
  Serial.println("Stopped");
  stop();
  delay(1000);

   // Run motor anticlockwise
  Serial.println("right turn");
  right();// anticlockwise
  
  delay(4000);

  // Stop motor
  Serial.println("Stopped");

  stop();
  delay(1000);


  Serial.println("left turn");
  left();// anticlockwise
  
  delay(4000);

  // Stop motor
  Serial.println("Stopped");

  stop();
  delay(1000);

}