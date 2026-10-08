"""Worker 入口占位；当前不读取或执行生成任务。"""

import logging


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.info("Worker 脚手架可用，未接入任务处理。")


if __name__ == "__main__":
    main()
