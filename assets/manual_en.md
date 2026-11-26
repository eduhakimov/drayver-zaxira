# Driver Backup: user guide

Save your drivers before reinstalling Windows, then reinstall them in one click.

## Backup
1. When the app opens it reads the third-party driver packages (`pnputil /enum-drivers`).
   The **Devices** column shows which device currently uses each driver.
2. Narrow the list with search, the class filter and “Hide Microsoft drivers”.
3. Tick the drivers you need and choose a backup folder in the right panel (a USB stick or drive D:).
4. Press **Back up**. Each driver is exported to `Class\name_version` and a
   `drivers_manifest.json` file is written. A ZIP archive can be created afterwards.

## Restore
1. On the **Restore** tab choose the backup folder or drop it onto the window.
2. With a manifest you see the computer name, date and driver list. Without one, `.inf` files are searched.
3. Tick the drivers and press **Install** (`pnputil /add-driver ... /subdirs /install`).
   Some drivers need a restart.

## Administrator rights
Export and restore require administrator rights. **Restart as administrator** in the top bar
reopens the app elevated.

## Commands
**Show commands** lists the `pnputil` commands that will run; copy them or save as a `.bat` file.
The **Log** tab keeps the output of every command.
