### 功能介绍

* 规则组命令： 循环依次顺序执行。
* 注入组命令：根据指定周期执行。该命令优先于规则组命令。但不会破坏当前正在执行的规则组命令。

程序启动后会自动依次顺序执行规则组命令。当注入组命令命令执行时间到来时，如果当前正在执行规则则命令，则会等待当前规则组命令执行完毕，然后执行。否则立刻执行。

```bash
λ python src\main.py -h
usage: main.py [-h] [-v] [-l] [-p COMxx] [-c COUNT] [-e] [PATH]

serial helper utility

positional arguments:
  PATH                  configuration file path(JSON)

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  -l, --list            list the current serial device of the system
  -p COMxx, --port COMxx
                        specify communication serial port name, such as COM1
  -c COUNT, --count COUNT
                        specify the count of command list executing
  -e, --echo            echo enable
```



### 配置文件示例

注意真正的json文件是不能包含注释的。

```ba
{
    "regular": [
    // 规则组命令
        [
            "regular_cmd0", // 命令字符串
            6000 // 命令执行时间， 单位ms
        ],
        [
            "regular_cmd1",
            6000
        ]
    ],
    "inject": [
     // 注入组命令
        [
            "inject_cmd1", // 命令字符串
            1000, // 命令执行时间， 单位ms
            10000 // 命令执行周期， 单位ms
        ],
        [
            "inject_cmd2",
            1000,
            15000
        ]
    ]
}
```







### 







