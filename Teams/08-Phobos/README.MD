# Smart Fault Detection Glasses

## Problem Statement:
Manual inspection for fault detection in industries is prone to human error and time consuming task. It is possible that minute defects or even major defects can go unnoticed sometimes due to the fatigue and repetitive work.

## Solution:
To address this problem, we developed a "Smart Fault Detection Glasses" using Raspberry Pi which detects the defects in real time using a camera module which is attached to the frame of the glasses. This is implemented using an ML model, designed by the team.

## Working:
- Camera module captures the image of the object that is to be tested and sends it to the Raspberry Pi
- Raspberry Pi processes the image, runs the ML model and inspects the image (OK/NOK)
- The processed data is sent to the server using Wi-Fi
- Server stores the inspection data
- Mobile application shows the inspection information from the database

## Hardware Components Used:
- Raspberry Pi 4 Model B
- Camera Module
- Battery
- Buzzer

## 🏗️ High-Level Architecture

![High-Level Architecture](./Teams/08-Phobos/assests/High-Level%20Architecture.jpeg)

## Project Structure:

## 🛠️ Hardware Components (Concept + Prototype)

- Raspberry Pi 4 Model B (conceptual / optional)  
- Camera Module / Webcam  
- Smart Glass Frame (prototype concept)  
- Battery Pack  
- Buzzer (for defect alert)  

---

## 💻 Software & Technologies Used

### 🔹 Frontend
- React.js  
- Firebase SDK  
- Chart.js  

### 🔹 Backend / Cloud
- Firebase Firestore (real-time database)  
- Firebase Hosting (optional)  

### 🔹 AI / Processing
- Python  
- OpenCV  
- TensorFlow / CNN Model  

---

## 📁 Project Structure


## 👥 Team Members

- Kavisha Sharma – AI Model Development  
- Preet Desai – Backend & Data Flow  
- Rudra Patel –   Dataset and 
- Sharmistha Kola – Hardware + Presentation
- Rahul – Frontend + Database + UI/UX Design 

## Future Scope:
- Deploy on actual smart glasses hardware  
- Add defect localization (heatmaps)  
- Voice alerts for defective parts  
- Predictive maintenance using historical data  
- Edge AI optimization for Raspberry Pi  
- Mobile app integration

## 🏁 Conclusion

This project demonstrates how **AI + IoT + Cloud** can transform traditional industrial inspection into an **automated, reliable, and real-time system**, reducing human error and improving efficiency.



