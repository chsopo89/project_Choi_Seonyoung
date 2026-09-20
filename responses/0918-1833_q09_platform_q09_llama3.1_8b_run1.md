Cisco Catalyst 스위치(IOS XE)에 Cisco 정품 광 SFP 모듈을 연결했으나 인식되지 않는다면, 다음의 순서로 장애를 점검해 보시길 바랍니다.

1.  **show interface** 명령어로 인터페이스 상태를 확인합니다. 이 명령어로 인터페이스 상태, 링크 상태, 속도,.duplex, 모듈 정보를 확인할 수 있습니다. 예를 들어, `show interface gigabitethernet 1/0/1` 명령어를 입력하여 인터페이스 상태를 확인할 수 있습니다.

    ```bash
    Switch# show interface gigabitethernet 1/0/1
    GigabitEthernet1/0/1 is up, line protocol is up
    Hardware is GigabitEthernet, address is 0012.3456.7890 (bia 0012.3456.7890)
    Description: 
    MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 1000 usec,
    reliability 255/255, txload 1/255, rxload 1/255
    Encapsulation ARPA, loopback not set
    Keepalive set (10 sec)
    Last clearing of "show interface" counters never
    Input queue: 0/200/0/0 (size/max/drops/flushes); Total output drops: 0
    Queue strategy: fifo
    Output queue: 0/40 (size/max)
    5 minute input rate 0 bits/sec, 0 packets/sec
    5 minute output rate 0 bits/sec, 0 packets/sec
    L2 Switching: enabled
    Flow control: enabled
    Auto-duplex: on
    Auto-speed: on
    ```

2.  **show module** 명령어로 모듈 정보를 확인합니다. 이 명령어로 모듈의 상태, 버전, 장착 여부, 속도, duplex, 모듈 ID를 확인할 수 있습니다. 예를 들어, `show module` 명령어를 입력하여 모듈 정보를 확인할 수 있습니다.

    ```bash
    Switch# show module
    Module 1 : 1      MgmtEth0/0/CPU0
    Module 2 : 2      MgmtEth0/0/CPU1
    Module 3 : 3      MgmtEth0/0/CPU2
    Module 4 : 4      MgmtEth0/0/CPU3
    Module 5 : 5      MgmtEth0/0/CPU4
    Module 6 : 6      MgmtEth0/0/CPU5
    Module 7 : 7      MgmtEth0/0/CPU6
    Module 8 : 8      MgmtEth0/0/CPU7
    Module 9 : 9      MgmtEth0/0/CPU8
    Module 10 : 10    MgmtEth0/0/CPU9
    Module 11 : 11    MgmtEth0/0/CPU10
    Module 12 : 12    MgmtEth0/0/CPU11
    Module 13 : 13    MgmtEth0/0/CPU12
    Module 14 : 14    MgmtEth0/0/CPU13
    Module 15 : 15    MgmtEth0/0/CPU14
    Module 16 : 16    MgmtEth0/0/CPU15
    Module 17 : 17    MgmtEth0/0/CPU16
    Module 18 : 18    MgmtEth0/0/CPU17
    Module 19 : 19    MgmtEth0/0/CPU18
    Module 20 : 20    MgmtEth0/0/CPU19
    Module 21 : 21    MgmtEth0/0/CPU20
    Module 22 : 22    MgmtEth0/0/CPU21
    Module 23 : 23    MgmtEth0/0/CPU22
    Module 24 : 24    MgmtEth0/0/CPU23
    Module 25 : 25    MgmtEth0/0/CPU24
    Module 26 : 26    MgmtEth0/0/CPU25
    Module 27 : 27    MgmtEth0/0/CPU26
    Module 28 : 28    MgmtEth0/0/CPU27
    Module 29 : 29    MgmtEth0/0/CPU28
    Module 30 : 30    MgmtEth0/0/CPU29
    Module 31 : 31    MgmtEth0/0/CPU30
    Module 32 : 32    MgmtEth0/0/CPU31
    Module 33 : 33    MgmtEth0/0/CPU32
    Module 34 : 34    MgmtEth0/0/CPU33
    Module 35 : 35    MgmtEth0/0/CPU34
    Module 36 : 36    MgmtEth0/0/CPU35
    Module 37 : 37    MgmtEth0/0/CPU36
    Module 38 : 38    MgmtEth0/0/CPU37
    Module 39 : 39    MgmtEth0/0/CPU38
    Module 40 : 40    MgmtEth0/0/CPU39
    Module 41 : 41    MgmtEth0/0/CPU40
    Module 42 : 42    MgmtEth0/0/CPU41
    Module 43 : 43    MgmtEth0/0/CPU42
    Module 44 : 44    MgmtEth0/0/CPU43
    Module 45 : 45    MgmtEth0/0/CPU44
    Module 46 : 46    MgmtEth0/0/CPU45
    Module 47 : 47    MgmtEth0/0/CPU46
    Module 48 : 48    MgmtEth0/0/CPU47
    Module 49 : 49    MgmtEth0/0/CPU48
    Module 50 : 50    MgmtEth0/0/CPU49
    Module 51 : 51    MgmtEth0/0/CPU50
    Module 52 : 52    MgmtEth0/0/CPU51
    Module 53 : 53    MgmtEth0/0/CPU52
    Module 54 : 54    MgmtEth0/0/CPU53
    Module 55 : 55    MgmtEth0/0/CPU54
    Module 56 : 56    MgmtEth0/0/CPU55
    Module 57 : 57    MgmtEth0/0/CPU56
    Module 58 : 58    MgmtEth0/0/CPU57
    Module 59 : 59    MgmtEth0/0/CPU58