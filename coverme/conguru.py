import confuse
from loguru import logger
import pathlib
from .log_folder import LogFolder
import shutil


def conguru_init(args, argv, config: confuse.Configuration, template: dict, log_dir: pathlib.Path, version: str):
    """
    Setup logging and configuration. Uses confuse for config. Uses loguru to save to disk. Saves all resulting config
    to disk. Creates a log folder based upon current timestamp
    :param args: Args from an argparse.ArgumentParser. "config" expected as a Path
    :param argv: Args from the command line. For logging only. (typically: sys.argv[1:])
    :param config: The confuse config to use
    :param template: The confuse template to enforce
    :param log_dir: The root of logging--a new folder will be created under here
    :param version: The version for logging
    """

    # Parse the config using confuse, bailing on failure
    try:

        if args.config:
            config.set_file(str(args.config))
        config.set_args(args, dots=True)

        logger.debug('configurations from {}', [x.filename for x in config.sources])

        valid_config = config.get(template)

    except confuse.ConfigError as ex:
        logger.critical("Problem parsing config: {}", ex)
        return

    # Cache old log path
    log_name = config['name'].get()

    try:
        LogFolder.get_latest_log_folder(log_dir / log_name)
    except FileNotFoundError:
        pass

    # Create log path
    LogFolder.set_path(log_dir, log_name)

    # Initialize logger
    logger.add(LogFolder.folder / "event.log", level="INFO")
    logger.info("Running program: {}", config['name'].get())
    logger.info("Version: {}", version)
    logger.info("Log folder: {}", LogFolder.folder)

    # Don't lost to stderr anymore
    logger.remove(0)

    # Copy configs
    # Straight copy
    orig_config = pathlib.Path(args.config)
    shutil.copyfile(str(orig_config), str(LogFolder.folder / orig_config.name))
    logger.info("CLI args: {}", argv)

    # Copy resulting config
    with open(LogFolder.folder / "config.yml", 'w') as f:
        f.write(config.dump())
