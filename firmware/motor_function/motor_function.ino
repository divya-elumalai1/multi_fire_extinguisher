#include <SoftwareSerial.h>
#include <AFMotor.h>
#include <Servo.h>


SoftwareSerial espSerial(A0, A1); // rx,tx



Servo my_servo;

// Create the motor object connected to M1–M4
AF_DCMotor motor1(1);
AF_DCMotor motor2(2);
AF_DCMotor motor3(3);
AF_DCMotor motor4(4);

int speed = 120; // 0-255
int servo_position = 0;

void setup() {
  // Start Serial Monitor
  Serial.begin(9600);
  espSerial.begin(9600);    // Communication with ESP32-CAM

  Serial.println("Ready to receive esp commands");
  delay(10);

  my_servo.attach(10); // SER0
  
  pinMode(2, OUTPUT);  // MIST
  pinMode(9, OUTPUT);  // Additional output pin

  digitalWrite(2,HIGH);
  digitalWrite(9,HIGH);

  my_servo.write(0); // by default open the trolley
}

void loop() {
  if (espSerial.available() > 0) {
    char input = espSerial.read();

    // Show what is received
    Serial.print("Received from ESP: ");
    Serial.println(input);
    // Ignore newline and carriage return characters
    if (input == '\r' || input == '\n') return;
    
    if (input == '1') {
      Serial.println("Opening servo...");
      for (servo_position = 100; servo_position >= 0; servo_position--) {
        my_servo.write(servo_position);
        delay(15);
      }
      Serial.println("Servo opened.");
    }
    
    else if (input == '0') {
      Serial.println("Closing servo...");
      for (servo_position = 0; servo_position <= 100; servo_position++) {
        my_servo.write(servo_position);
        delay(15);
      }
      Serial.println("Servo closed.");
    }
    

    else if (input == '2') {
      digitalWrite(2, LOW);
      Serial.println("Mist ON ");
    }

    else if (input == '3') {
      digitalWrite(2, HIGH);
      Serial.println("Mist Off");
    }

    else if (input == '4') {
      digitalWrite(9, LOW);
      Serial.println("Motor ON");
    }

    else if (input == '5') {
      digitalWrite(9, HIGH);
      Serial.println("Motor Off");
    }

    else if (input == '6') {
      forward();
      Serial.println("Forward");
    }

    else if (input == '7') {
      backward();
      Serial.println("Backward");
    }

    else if (input == '8') {
      right();
      Serial.println("Right");
    }

    else if (input == '9') {
      left();
      Serial.println("Left");
    }

    else if (input == 'p') {
      stop();
      Serial.println("Stop");
    }

  
  }
}

