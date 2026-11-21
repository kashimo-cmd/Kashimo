# KASHIMO
### Tracked Robot for Remote Inspection of Electrical Cable Galleries

**TSYP14 – IAS Challenge | Engineering Project**

Kashimo is a tracked inspection robot designed to help technicians inspect electrical cable galleries remotely. It carries a camera, lighting and onboard computing to transmit live video, record inspection evidence, monitor its position and support the detection of cable anomalies without requiring a technician to enter the gallery.

**Repository:** [kashimo-cmd/Kashimo](https://github.com/kashimo-cmd/Kashimo)  
**Development status:** Prototype and integration phase  
**Main computer:** Raspberry Pi 5 (4 GB RAM)  
**Communication:** Wi-Fi  
**Operator interface:** PC-based web dashboard

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem and Objectives](#2-problem-and-objectives)
3. [Inspection Environment](#3-inspection-environment)
4. [System Features](#4-system-features)
5. [System Architecture](#5-system-architecture)
6. [Mechanical Design](#6-mechanical-design)
7. [Electrical and Hardware Design](#7-electrical-and-hardware-design)
8. [Software Architecture](#8-software-architecture)
9. [Artificial Intelligence](#9-artificial-intelligence)
10. [Inspection Workflow](#10-inspection-workflow)
11. [Power System and Battery Selection](#11-power-system-and-battery-selection)
12. [Development and Testing](#12-development-and-testing)
13. [Repository Structure](#13-repository-structure)
14. [Budget](#14-budget)
15. [Safety and Risk Management](#15-safety-and-risk-management)
16. [Current Limitations and Future Improvements](#16-current-limitations-and-future-improvements)
17. [Team and Acknowledgements](#17-team-and-acknowledgements)
18. [License](#18-license)

---

## 1. Project Overview

Kashimo is a remotely operated tracked robot developed for the inspection of underground electrical cable galleries.

The robot is intended to travel through narrow and potentially difficult environments while transmitting visual information to an operator located outside the gallery. Its onboard Raspberry Pi 5 handles robot control, communication, video processing, data recording and AI inference.

The project combines four main engineering areas:

- **Mechanical engineering:** tracked mobility, chassis design, camera positioning and physical protection.
- **Electronics and embedded systems:** motor control, power distribution, sensors, lighting and communication hardware.
- **Software engineering:** robot control, wireless communication, video streaming, operator interface and data logging.
- **Artificial intelligence:** visual anomaly detection to assist the operator during inspection.

The objective is to develop a practical inspection platform that improves access to visual information, reduces the need for manual entry and provides organized inspection evidence.

## 2. Problem and Objectives

### 2.1 The problem

Inspecting electrical cable galleries can require technicians to access confined underground spaces and visually examine long sections of installed cables.

This process can be time-consuming and may expose personnel to difficult working conditions. Faults can also be difficult to locate precisely when the inspection relies only on manual observation.

Potential anomalies that Kashimo is intended to help identify include:

- Damaged or cut cables.
- Burn marks and visible overheating damage.
- Water ingress and signs of moisture.
- Other visible irregularities along the cable route.

### 2.2 Project objectives

Kashimo aims to:

1. Move through the gallery using a tracked drive system.
2. Provide live visual access through a remotely operated camera.
3. Illuminate dark inspection areas.
4. Transmit video and robot telemetry over Wi-Fi.
5. Estimate the robot's travelled distance and position.
6. Associate detected anomalies with an approximate slab location.
7. Record photographs, screenshots and inspection events.
8. Run an AI anomaly-detection pipeline on the Raspberry Pi 5.
9. Stop the motors automatically if the communication link is lost.

### 2.3 Design philosophy

The robot is designed around remote operation and operator supervision. AI-generated alerts are intended to assist the operator, not replace human verification.

The project prioritizes practical integration, safe stopping behaviour, maintainable software and measurable testing over features that cannot be reliably demonstrated.

## 3. Inspection Environment

Kashimo is designed around the following inspection conditions:

| Parameter | Project requirement |
|---|---|
| Environment | Underground electrical cable gallery |
| Gallery length | More than 30 metres |
| Gallery width | Approximately 2 metres |
| Gallery depth | Approximately 1.5 metres |
| Covering | Removable slabs |
| Slab width | Approximately 50 cm |
| Communication | Wi-Fi |
| Inspection method | Remote operation from outside the gallery |
| Main visual targets | Electrical cables and visible anomalies |

The robot must be designed to operate in a gallery containing electrical cables and possible electromagnetic interference.

The mechanical design must also consider the opening available when a slab is removed, the gallery floor, turns, obstacles and the space required for the camera and lighting assembly.

The actual dimensions and geometry of the robot will be validated against the access opening and the inspection route before final fabrication.

## 4. System Features

### 4.1 Tracked mobility

A two-motor tracked drive system provides forward, reverse and turning movements. Motor encoders provide movement feedback for distance estimation.

### 4.2 Live video inspection

A USB camera connected to the Raspberry Pi 5 provides visual access to the gallery. The video is transmitted to the operator's computer.

### 4.3 Inspection lighting

A 5 V addressable WS2812B RGB LED strip provides controllable illumination. The strip will be cut to the required length for the robot.

### 4.4 Remote control

The operator controls the robot through a PC dashboard. Commands are transmitted wirelessly to the Raspberry Pi.

### 4.5 Position estimation

Motor encoder measurements and inertial sensor data are intended to estimate travelled distance, direction and orientation. The estimated path position can then be associated with the gallery's slab layout.

### 4.6 AI-assisted anomaly detection

The AI subsystem processes camera images and identifies visual patterns that may indicate anomalies. Alerts are displayed to the operator together with the corresponding inspection evidence.

### 4.7 Data recording

The system is designed to preserve inspection evidence, including images, screenshots, anomaly events and position information.

### 4.8 Communication-loss protection

A communication watchdog is included in the control design. If valid control messages stop arriving, the motor outputs are disabled.

---

## 5. System Architecture

Kashimo is organized into three main operational components.

### 5.1 Robot hardware

The physical robot contains:

- Raspberry Pi 5.
- Two geared DC motors with encoders.
- Two BTS7960 motor-driver modules.
- USB camera.
- Addressable LED lighting.
- Power conversion modules.
- Sensors and supporting electronics.
- Tracked chassis and mechanical camera assembly.

### 5.2 Raspberry Pi software

The Raspberry Pi is the main onboard computer. It is responsible for:

- Reading sensor information.
- Controlling the motors.
- Managing the robot's operating state.
- Receiving operator commands.
- Transmitting telemetry.
- Capturing and streaming video.
- Recording inspection data.
- Running AI inference.

### 5.3 Operator computer

The operator computer runs a browser-based dashboard served by a Python application.

The dashboard is intended to display:

- Live camera feed.
- Robot operating state.
- Obstacle distances.
- Communication status.
- Estimated distance and slab position.
- AI alerts.
- Inspection logs.
- Robot control commands.

### 5.4 Data flow

```text
                 OPERATOR COMPUTER
              +----------------------+
              |   Web Dashboard      |
              |                      |
              | Live Video           |
              | Robot Controls       |
              | Telemetry            |
              | Alerts and Logs      |
              +----------+-----------+
                         |
                      Wi-Fi
                         |
              +----------v-----------+
              |    Raspberry Pi 5    |
              |                      |
              | Robot Controller     |
              | WebSocket Server     |
              | Video Pipeline       |
              | AI Inference         |
              | Event Recording      |
              +----+------------+----+
                   |            |
             Motor Control   Camera
                   |            |
             +-----v-----+  +---v------+
             | BTS7960   |  | USB      |
             | Drivers  |  | Camera   |
             +-----+-----+  +----------+
                   |
              DC Motors
              with Encoders

          Sensors, lighting and power
          are integrated into the robot.
```

The Raspberry Pi is the central processing unit. The PC provides the operator interface, while the robot performs its control and AI tasks onboard.

---

## 6. Mechanical Design

### 6.1 Chassis

The robot uses a tracked chassis to provide traction and maneuverability on the gallery floor.

The mechanical development is divided into two stages:

- **Prototype:** 3D-printed components will be used to validate dimensions, assembly, component placement and mechanical movement.
- **Final robot:** the final chassis will be fabricated using a suitable structural material and manufacturing process. It will not be a fully 3D-printed chassis.

This separation allows the team to validate the mechanical concept before committing to final fabrication.

### 6.2 Drive system

The mobility system uses two JGB37-520 DC geared motors rated at 12 V and 110 RPM, with integrated encoders.

The two motors are controlled independently, allowing differential steering:

- Both motors forward: forward movement.
- Both motors reverse: backward movement.
- Different motor speeds: curved movement.
- Opposite motor directions: turning in place.

The motor drivers are BTS7960B H-bridge modules.

### 6.3 Camera assembly

The USB camera is mounted to provide a useful view of the cables and surrounding gallery.

The design also considers an adjustable camera orientation so that the operator can inspect different areas without moving the entire robot.

### 6.4 Lighting assembly

The WS2812B RGB strip is mounted on the robot to illuminate the inspection area.

The required strip length will be cut from the purchased 1-metre strip. Lighting intensity and camera exposure will need to be evaluated together to obtain readable images.

### 6.5 Mechanical validation

The prototype will be evaluated for:

- Track alignment and tension.
- Motor mounting and torque transfer.
- Chassis stability.
- Camera visibility.
- Lighting coverage.
- Cable protection and routing.
- Access through the slab opening.
- Maneuverability in the gallery.

---

## 7. Electrical and Hardware Design

### 7.1 Main computing unit

The robot uses a **Raspberry Pi 5 with 4 GB RAM**.

The board is already owned by the project and is therefore excluded from the remaining purchasing budget.

It is responsible for the robot's embedded software, communication, video pipeline and AI inference.

### 7.2 Hardware bill of materials

The following table lists the components provided for the current hardware design.

| Quantity | Component | Reference / specification | Function |
|---:|---|---|---|
| 1 | MicroSD card | Class 10, 32 GB — 0800-01000 | Raspberry Pi storage |
| 1 | Addressable RGB LED strip | WS2812B, 5 V, 60 LEDs/m, 5050, 1 m — 1500-10107 | Inspection lighting |
| 1 | N-channel MOSFET | IRLZ44, 60 V, 50 A, TO-220 — 3139-00059 | Electronic switching |
| 2 | Geared DC motors | JGB37-520, 12 V, 110 RPM, with encoders — 1900-74832 | Robot mobility |
| 2 | Motor drivers | BTS7960B, H-bridge — 1800-00478 | Motor power control |
| 1 | Adjustable DC-DC converter | XL4015, 5 A, 75 W, USB output — 0800-95935 | Voltage conversion |
| 2 | Adjustable buck converters | LM2596 — 0800-01352 | Regulated power rails |
| 1 | Rocker switch | Red illuminated, DPST — 0507-00068 | Main power switching |
| 1 set | Battery connectors | XT60 male and female — 0500-11701 | Battery connection |
| 1 | Heat-shrink tubing | 12/6 mm, per metre — 5600-00309 | Electrical insulation |
| 3 | Resistors | 1 kΩ | Signal conditioning |
| 3 | Resistors | 2 kΩ | Signal conditioning |
| 3 | Resistors | 220 Ω | Signal and LED circuits |
| 2 | Resistors | 10 kΩ | Pull-up / pull-down circuits |
| 6 | Ceramic capacitors | 100 nF | Noise suppression |
| 2 | Electrolytic capacitors | 1000 µF, 35 V — 1300-00015 | Supply filtering |
| 1 | USB card reader | USB 2.0 microSD reader — 0800-09018 | Memory-card access |
| 1 | Perforated board | 5 × 7 cm, single-sided — 0400-01144 | Circuit assembly |
| 4 | Clip-on ferrite cores | 0700-06184 | Electromagnetic interference reduction |
| 1 | Raspberry Pi | Raspberry Pi 5, 4 GB | Main onboard computer |
| 1 | Camera | USB 8 MP camera for Raspberry Pi | Visual inspection |

The camera description reflects the current project selection; its exact model and supported video modes must be confirmed during integration.

### 7.3 Additional integration requirements

The complete robot design also requires the appropriate supporting hardware for sensing, mounting, protection and power management.

The design plan includes:

- Ultrasonic distance sensing.
- Inertial measurement using an MPU6050.
- Encoder feedback from the drive motors.
- Camera mounting and mechanical positioning.
- Suitable battery protection and charging equipment.
- A stable power supply for the Raspberry Pi.
- Proper connectors, wiring and mechanical protection.

These items must be checked against the team's available stock and final assembly requirements before the complete hardware inventory is considered closed.

### 7.4 Motor control

Each motor is connected to a BTS7960B driver.

The Raspberry Pi sends control signals to the drivers through the GPIO interface. The motor-enable circuit is designed to default to a disabled state during startup or controller failure.

Motor current, driver temperature and voltage drops must be checked under real operating loads. The advertised peak current of a driver module must not be treated as its guaranteed continuous operating current.

### 7.5 Electromagnetic compatibility

Electrical cable galleries can expose electronic systems to interference.

The design therefore includes:

- Ferrite cores on appropriate wiring.
- Short and organized signal connections.
- Separation between motor power wiring and sensitive signal wiring.
- Local supply decoupling.
- A common grounding strategy.
- Testing of Wi-Fi reliability with the motors operating.

The final wiring layout must be validated on the assembled robot.

---

## 8. Software Architecture

### 8.1 Software overview

The software is divided between the Raspberry Pi and the operator computer.

The Raspberry Pi handles time-sensitive robot functions and onboard processing. The operator computer provides the dashboard and user interaction.

### 8.2 Raspberry Pi software

The planned onboard software is based on Python 3.11 and Raspberry Pi OS Lite 64-bit.

Main responsibilities include:

- Motor and sensor management.
- Robot state and safety logic.
- WebSocket communication.
- Video capture and streaming.
- AI inference.
- Event and inspection-data recording.

### 8.3 Operator computer software

The PC side is based on:

- Python 3.11.
- FastAPI.
- Uvicorn.
- WebSocket communication.
- HTML, CSS and JavaScript.
- A browser-based operator dashboard.

The dashboard is designed to work without a frontend framework or an internet connection once the required software is installed.

### 8.4 Communication protocol

The robot and operator computer communicate through Wi-Fi.

The planned communication layer uses JSON messages over WebSocket.

The protocol is intended to carry:

- Movement commands.
- Robot state.
- Sensor measurements.
- Position information.
- AI status and alerts.
- Heartbeats and synchronization messages.

A heartbeat mechanism is used to verify that the operator connection remains active.

The design specifies a 100 ms heartbeat interval and a 500 ms watchdog timeout. If valid control messages are no longer received, the motor outputs are disabled.

These values are engineering targets that must be verified during testing.

### 8.5 Video streaming

The planned video pipeline uses:

- USB camera capture.
- FFmpeg for video processing.
- MediaMTX for video transport.
- WebRTC for browser-based live viewing.
- MJPEG as a fallback mode.

The design target is a 1280 × 720 stream at 15 frames per second. Actual resolution, frame rate and latency depend on the camera, Raspberry Pi load and wireless conditions.

### 8.6 Data storage

SQLite is planned for local event storage.

The system is intended to record:

- Inspection events.
- Anomaly alerts.
- Position and slab information.
- Image references.
- Synchronization information.

This allows the robot to retain important inspection events if the wireless link temporarily drops.

---

## 9. Artificial Intelligence

### 9.1 Purpose

The AI subsystem is designed to assist with the visual inspection of electrical cables.

It processes images from the onboard camera and identifies visual patterns that differ from normal inspection conditions.

Potential targets include:

- Cable cuts and visible damage.
- Burn marks.
- Water ingress and abnormal moisture-related visual patterns.
- Other unusual visual conditions.

The AI system is an inspection aid. Its output must be reviewed by the operator before a fault is confirmed.

### 9.2 Processing location

AI inference is planned to run directly on the Raspberry Pi 5.

This avoids making the robot entirely dependent on a continuous wireless connection to a remote AI computer.

Model training and experimentation can be performed on a separate computer, while the selected model is exported for onboard inference.

### 9.3 Detection approach

PatchCore is the proposed initial anomaly-detection approach.

PatchCore learns visual representations of normal images and identifies image regions that differ from the learned normal patterns. This makes it a candidate for inspection situations where representative normal images are easier to collect than labelled examples of every possible fault.

The model selection is not considered final until alternatives have been benchmarked on the Raspberry Pi.

The design plan also considers EfficientAD-S as a lightweight alternative.

### 9.4 Dataset development

The planned AI development process has three stages:

1. **Initial experimentation:** use available public anomaly-detection datasets to build and evaluate the pipeline.
2. **Normal gallery data:** collect images using the actual camera and lighting arrangement in a representative mock inspection environment.
3. **Validation:** introduce controlled visual anomalies and evaluate detection performance.

The final model should be evaluated using relevant metrics, including precision, recall, F1-score, AUROC, inference time and false alarms per inspection run.

### 9.5 AI integration

The AI software is designed as a separate module so that the model can be updated without rewriting the robot controller.

The planned pipeline includes:

1. Obtain a camera frame.
2. Check whether the robot and camera are in a suitable inspection state.
3. Run the anomaly detector.
4. Apply the alert threshold and consecutive-detection rules.
5. Save the relevant image and heatmap.
6. Send the alert to the robot controller.
7. Display the alert in the operator dashboard.

The initial software integration can use a dummy detector while the final trained model is being prepared.

A dummy detection must always be clearly labelled as test output and must never be confused with a real inspection result.

---

## 10. Inspection Workflow

The intended inspection sequence is as follows.

### 10.1 Preparation

1. The inspection team opens the required access slab.
2. The robot is checked before deployment.
3. The wireless router and operator computer are prepared.
4. The robot is lowered into the gallery using the approved handling method.

### 10.2 Startup

1. The robot is powered on.
2. The Raspberry Pi starts the controller and communication services.
3. The camera and lighting are initialized.
4. The sensor readings are checked.
5. The operator opens the dashboard and verifies the connection.

### 10.3 Remote inspection

1. The operator views the live camera feed.
2. The robot is driven along the gallery.
3. The operator observes cable conditions and surrounding obstacles.
4. The system estimates travelled distance and position.
5. Images and screenshots can be recorded for later review.
6. The AI subsystem analyzes suitable camera frames and generates alerts when its detection rules are met.

### 10.4 Communication loss

If the wireless connection is lost:

1. The watchdog detects the missing control messages.
2. Motor outputs are disabled.
3. The robot enters its communication-loss safety state.
4. Local recording and event storage are designed to continue.
5. When communication returns, stored events can be synchronized with the operator computer.

### 10.5 Completion

The operator returns the robot to the access point, stops the drive system and retrieves the robot.

Inspection images, logs and alerts can then be reviewed.

---

## 11. Power System and Battery Selection

### 11.1 Power requirements

The battery must supply the robot's motors, Raspberry Pi, camera, lighting and supporting electronics.

The design must account for both normal operating consumption and short current peaks during motor startup, turning or mechanical resistance.

The Raspberry Pi requires a stable regulated 5 V supply capable of supporting its peak load. Motor power should be separated from sensitive logic power to reduce electrical noise and prevent supply disturbances from resetting the computer.

### 11.2 Preliminary battery selection

The preliminary battery candidate is a **3S LiPo battery with approximately 5000 mAh capacity**.

| Parameter | Preliminary selection |
|---|---|
| Battery type | LiPo |
| Configuration | 3S |
| Nominal voltage | 11.1 V |
| Fully charged voltage | 12.6 V |
| Capacity | Approximately 5000 mAh |
| Main connector | XT60 |
| Runtime objective | At least 40 minutes under the defined test conditions |

This is a proposed selection, not a confirmed purchased component or a validated runtime result.

The final discharge rating must be selected using the measured or documented stall current of both motors, the driver requirements and the total electrical load. The battery must also be equipped with a compatible balance charger, appropriate protection, a correctly rated fuse and a low-voltage monitoring strategy.

### 11.3 Power distribution

The planned electrical architecture separates the motor supply from regulated electronic loads.

- Battery supply: motor drivers and other loads compatible with the battery voltage.
- Regulated 5 V rail: Raspberry Pi and suitable 5 V electronics.
- Additional regulated rail: lighting and other loads according to their electrical requirements.

The XL4015 and LM2596 modules must be assigned only after their output voltage, current capacity, thermal limits and actual load requirements have been checked.

The WS2812B strip requires a suitable regulated 5 V supply. It must not be connected directly to the 3S battery.

### 11.4 Runtime validation

Battery runtime will be measured with the complete system operating, including the camera, lighting, motors, communication and AI inference.

The target of at least 40 minutes must be demonstrated through a full-load test rather than estimated from battery capacity alone.

---

## 12. Development and Testing

### 12.1 Development approach

The project is developed in stages so that mechanical, electrical and software components can be tested independently before full integration.

The software architecture includes a mock hardware mode. This allows parts of the PC interface and control system to be developed without requiring the physical robot for every test.

### 12.2 Main validation tests

| Test area | Validation objective |
|---|---|
| Mobility | Verify forward, reverse, turning and track behaviour |
| Motor control | Verify independent motor control and safe stopping |
| Communication | Measure Wi-Fi reliability along the inspection route |
| Watchdog | Verify motor shutdown after communication loss |
| Video | Measure stream stability, frame rate and latency |
| Camera | Check image clarity at representative cable distances |
| Lighting | Verify illumination and image quality |
| Position | Compare encoder-based distance with measured distance |
| Slab estimation | Verify approximate slab identification |
| AI | Measure detection performance and inference time on the Pi |
| Power | Measure voltage stability and current consumption |
| Runtime | Verify the full-load runtime target |
| Mechanical | Verify access, turning, stability and component mounting |

### 12.3 Key engineering targets

The current design plan defines the following targets for validation:

| Parameter | Target |
|---|---|
| Gallery inspection distance | More than 30 m |
| Communication watchdog | Motor outputs disabled within 0.5 s |
| Heartbeat interval | 100 ms |
| Video frame rate | 15 FPS |
| Video resolution | 1280 × 720 |
| WebRTC latency | 0.5 s or less |
| Position estimation | Within approximately one slab |
| AI inference time | 300 ms or less per frame |
| AI process memory | 1.5 GB or less |
| Battery runtime | At least 40 minutes |

These are design and validation targets. They must not be interpreted as achieved performance until the corresponding tests have been completed and documented.

### 12.4 Test environment

A representative mock gallery will be used to test robot movement, turning, camera visibility, communication and position estimation before relying on the system in the real inspection environment.

Test results should include the test conditions, measured values, observations and any corrective actions.

---

## 13. Repository Structure

The repository is organized by engineering domain to keep the project maintainable and make collaboration easier.

```text
Kashimo/
│
├── hardware/
│   ├── electronics/
│   ├── wiring/
│   ├── components/
│   └── datasheets/
│
├── software/
│   ├── raspberry_pi/
│   │   ├── controller/
│   │   ├── communication/
│   │   ├── camera/
│   │   └── sensors/
│   │
│   └── operator_pc/
│       ├── server/
│       ├── dashboard/
│       └── communication/
│
├── ai/
│   ├── datasets/
│   ├── training/
│   ├── models/
│   └── inference/
│
├── conception/
│   ├── cad/
│   ├── chassis/
│   └── fabrication/
│
├── docs/
│   ├── technical/
│   ├── diagrams/
│   └── testing/
│
├── scripts/
│
└── README.md
```

### Folder responsibilities

| Folder | Purpose |
|---|---|
| `hardware/` | Electronic components, wiring documentation and datasheets |
| `software/raspberry_pi/` | Embedded software running on the robot |
| `software/operator_pc/` | PC server and operator dashboard |
| `ai/` | Datasets, training resources, model files and inference code |
| `conception/` | CAD models, chassis development and fabrication documentation |
| `docs/` | Technical documents, diagrams and test reports |
| `scripts/` | Utility and development scripts |

The repository is intended to contain the project's source code and technical documentation. Large datasets, generated recordings and model artifacts should be managed separately when appropriate.

---

## 14. Budget

The project follows a provisional overall budget ceiling of **750 TND**.

The Raspberry Pi 5 is already owned and is excluded from the remaining purchasing budget.

The budget must account for the components and materials required to complete the robot, including:

- Motors and motor drivers.
- Battery and charging equipment.
- Power conversion and protection.
- Lighting and electrical components.
- Mechanical fabrication.
- Wiring, connectors and assembly materials.
- Testing and contingency expenses.

The final purchasing balance must be based on actual supplier prices and confirmed stock. The 750 TND figure is the project budget ceiling, not a claim that the complete robot has already been purchased or assembled within that amount.

---

## 15. Safety and Risk Management

Kashimo is intended for inspection around electrical infrastructure. Its use must therefore be treated as a controlled engineering activity.

### 15.1 Electrical safety

- The robot must not be treated as electrically insulated or certified for direct contact with energized conductors.
- Electrical protection, insulation, connector quality and enclosure design must be evaluated before deployment.
- Battery wiring must include appropriate protection against short circuits and overcurrent.
- The battery must be charged and stored using the correct equipment and procedures.

### 15.2 Communication safety

- The robot must stop when valid control messages are lost.
- Motor outputs must default to a disabled state during startup or controller failure.
- Reconnection must not automatically resume movement without an explicit operator command.

### 15.3 Mechanical safety

- Tracks and moving mechanisms must be protected against cable snagging.
- The chassis must be stable during movement and retrieval.
- The robot must be recoverable from the access opening.
- Mechanical testing must be completed before use in the actual gallery.

### 15.4 Environmental protection

The electronics and connectors must be protected against dust, humidity, vibration and accidental contact with surrounding infrastructure.

The final enclosure and wiring arrangement must be validated under representative conditions.

---

## 16. Current Limitations and Future Improvements

Kashimo is an engineering prototype under development. Several aspects require physical validation and refinement.

### Current limitations

- The final chassis and mechanical dimensions require validation.
- Battery discharge capability and full-load runtime require measurement.
- Wi-Fi performance must be tested along the actual inspection route.
- Encoder and inertial measurements require calibration.
- AI performance depends on collecting representative gallery images.
- The final camera model and video settings must be confirmed.
- The system has not yet demonstrated all stated performance targets through complete integrated tests.

### Planned improvements

- Finalize and fabricate the structural chassis.
- Improve protection against dust, humidity and electrical interference.
- Calibrate position estimation and slab association.
- Optimize the AI model for Raspberry Pi inference.
- Improve video quality and wireless reliability.
- Add more complete inspection reports and event visualization.
- Expand testing using representative cable-gallery conditions.

---

## 17. Team and Acknowledgements

Kashimo is developed as part of the **TSYP14 IAS Challenge**.

The project brings together mechanical design, electronics, embedded software, computer vision and system integration.

Contributors and responsibilities are maintained as the project team and work allocation are finalized.

The project also relies on the documentation and open-source tools associated with its selected hardware and software components.

---

## 18. License

No open-source license has been declared for this repository at the current development stage.

Until a license is added, the repository should not be assumed to grant permission for redistribution, modification or commercial use.
