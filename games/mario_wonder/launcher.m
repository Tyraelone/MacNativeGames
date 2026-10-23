#import <AppKit/AppKit.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void set_path(const char *name, NSString *value) {
    setenv(name, value.fileSystemRepresentation, 1);
}

int main(void) {
    @autoreleasepool {
        NSString *root = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"game"];
        NSString *binary = [root stringByAppendingPathComponent:@"build/mario-wonder-native"];
        NSString *data = [NSHomeDirectory() stringByAppendingPathComponent:
            @"Library/Application Support/MacNativeGames/MarioWonder"];
        NSString *logs = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/MacNativeGames"];
        NSFileManager *fm = NSFileManager.defaultManager;
        if (access(binary.fileSystemRepresentation, X_OK) ||
            ![fm createDirectoryAtPath:data withIntermediateDirectories:YES attributes:nil error:nil] ||
            ![fm createDirectoryAtPath:logs withIntermediateDirectories:YES attributes:nil error:nil]) {
            NSAlert *alert = [NSAlert new];
            alert.messageText = @"无法启动超级马里奥兄弟 惊奇";
            alert.informativeText = @"游戏文件不存在，或无法创建用户数据目录。";
            [alert runModal];
            return 1;
        }
        NSString *profile = [data stringByAppendingPathComponent:@"profile"];
        NSString *slot = [data stringByAppendingPathComponent:@"game-slot"];
        NSString *cache = [data stringByAppendingPathComponent:@"shader-cache"];
        NSString *proof = [data stringByAppendingPathComponent:@"proof"];
        for (NSString *path in @[profile, slot, cache, proof])
            if (![fm createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:nil]) return 1;
        set_path("TOTK_PROFILE_DIR", profile);
        set_path("TOTK_GAME_SLOT_DIR", slot);
        set_path("TOTK_SHADER_CACHE", cache);
        set_path("TOTK_ROMFS_PROOF_DIR", proof);
        set_path("TOTK_ROMFS", [root stringByAppendingPathComponent:@"romfs"]);
        set_path("TOTK_SHARED_FONTS", [root stringByAppendingPathComponent:@"extracted/firmware/shared-fonts"]);
        set_path("TOTK_PROFILE_IMAGE", [root stringByAppendingPathComponent:@"build/local-avatar.jpg"]);
        setenv("TOTK_ROMFS_PATCHES", "0", 1);
        setenv("TOTK_GPU_ALLOW_SUBMIT", "1", 1);
        setenv("TOTK_GPU_MIDCLEAR", "1", 1);
        setenv("TOTK_SLOT_OWNER", "user", 1);
        setenv("TOTK_SLOT_PURPOSE", "player", 1);
        unsetenv("TOTK_AUTOLOAD");
        unsetenv("TOTK_INPUT_FILE");
        unsetenv("TOTK_INPUT_SCRIPT");
        unsetenv("TOTK_HEADLESS");
        unsetenv("TOTK_ROMFS_PATCHES_OUT");
        unsetenv("TOTK_SHADER_SEED");
        NSString *log = [logs stringByAppendingPathComponent:
            [NSString stringWithFormat:@"mario-wonder-%ld.log", (long)getpid()]];
        FILE *file = fopen(log.fileSystemRepresentation, "w");
        if (file) { dup2(fileno(file), STDOUT_FILENO); dup2(fileno(file), STDERR_FILENO); fclose(file); }
        if (chdir(root.fileSystemRepresentation)) return 1;
        char *const args[] = {(char *)binary.fileSystemRepresentation, "rewritten", "boot", NULL};
        execv(args[0], args);
        fprintf(stderr, "Mario Wonder execv: %s\n", strerror(errno));
        return 1;
    }
}
