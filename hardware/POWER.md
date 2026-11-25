# Power and electrical safety (design, not built)

From [design.md](../docs/design.md) 8.2 and 8.5.
```
3S LiPo (9.9-12.6 V) - XT60 - fuse 15 A - switch -+- BTS7960 L - motor L
 (low-voltage alarm on balance lead)              +- BTS7960 R - motor R
                                                  +- LED bar via MOSFET (12 V, up the rod)
                                                  +- Buck A 5.1 V >=5 A - Pi 5, BTS logic, HC-SR04 x3
                                                  +- Buck B 5-6 V 5 A - servos only (+1000 uF)
```
- Star ground at the battery minus. Two bucks so servo and motor noise cannot reset the Pi.
- Motor enables tied to GPIO 24 with a 10 k pull-down: Pi off or booting means motors off.
- 100 nF across each motor, ferrites, twisted motor wires away from camera and signal wires.
- MPU6050 flat on the chassis near the centre, away from motors and 12 V wires. No magnetometer.
- Camera on a USB 2.0 port.
- Runtime [CALC][EST]: about 43 W, 35 usable Wh, about 49-61 min, minus AI load. Not measured: test T12.

## Safety
- Sealed electronics box (about IP54 [EST]).
- 380 V cables plus water plus a conductive chassis is a shock risk when lifting the robot out. Plastic chassis and handle, no exposed metal. ACTIA safety must confirm; nobody on the team is a certified safety engineer.
- No compliance or certification is claimed.
