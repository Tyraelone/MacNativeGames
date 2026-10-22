/* Native Castlevania bundle entry. The recompiled ARM64 host executes verified
   rewritten modules directly; writable state stays in the player's Library. */
#import <AppKit/AppKit.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static BOOL directory(NSString *path) {
    return [[NSFileManager defaultManager] createDirectoryAtPath:path
        withIntermediateDirectories:YES attributes:nil error:nil];
}
static NSString *choice(const char *key, NSString *fallback) {
    const char *v=getenv(key); return v&&*v?@(v):fallback;
}
int main(int argc,char **argv) {
    @autoreleasepool {
        NSString *root=[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"castlevania"];
        NSString *host=[root stringByAppendingPathComponent:@"build/totk-native"];
        NSString *icon=[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"AppIcon.icns"];
        NSString *images=[root stringByAppendingPathComponent:@"rewritten"];
        NSString *romfs=[root stringByAppendingPathComponent:@"main/romfs"];
        NSString *addons=[root stringByAppendingPathComponent:@"addons"];
        BOOL present=access(icon.fileSystemRepresentation,R_OK)==0
            && access(host.fileSystemRepresentation,X_OK)==0
            && access([images stringByAppendingPathComponent:@"main.patched.bin"].fileSystemRepresentation,R_OK)==0
            && access([images stringByAppendingPathComponent:@"sdk.patched.bin"].fileSystemRepresentation,R_OK)==0
            && access([images stringByAppendingPathComponent:@"subsdk0.patched.bin"].fileSystemRepresentation,R_OK)==0
            && access([romfs stringByAppendingPathComponent:@"romfs.bin"].fileSystemRepresentation,R_OK)==0
            && access([romfs stringByAppendingPathComponent:@"runtime-index.bin"].fileSystemRepresentation,R_OK)==0;
        if(argc>1&&!strcmp(argv[1],"--check")){puts(present?"ok":"missing files");return present?0:1;}
        if(!present){NSAlert *a=[NSAlert new];a.messageText=@"游戏文件不完整";[a runModal];return 1;}
        NSString *data=[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/MacNativeGames/Castlevania"];
        NSString *logs=[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/MacNativeGames/Castlevania"];
        NSString *profile=choice("TOTK_PROFILE_DIR",[data stringByAppendingPathComponent:@"profile"]);
        NSString *slot=choice("TOTK_GAME_SLOT_DIR",[data stringByAppendingPathComponent:@"game-slot"]);
        NSString *cache=choice("TOTK_SHADER_CACHE",[data stringByAppendingPathComponent:@"shader-cache/castlevania-native-v1"]);
        if(!directory(data)||!directory(logs)||!directory(profile)||!directory(slot)||!directory(cache)){
            NSAlert *a=[NSAlert new];a.messageText=@"无法建立游戏数据目录";[a runModal];return 1;
        }
        NSString *commands=choice("TOTK_INPUT_FILE",[data stringByAppendingPathComponent:@"input.txt"]);
        FILE *cf=fopen(commands.fileSystemRepresentation,"w");if(cf)fclose(cf);
        setenv("TOTK_PROFILE_DIR",profile.fileSystemRepresentation,1);
        setenv("TOTK_GAME_SLOT_DIR",slot.fileSystemRepresentation,1);
        setenv("TOTK_SHADER_CACHE",cache.fileSystemRepresentation,1);
        setenv("TOTK_ROMFS_PROOF_DIR",data.fileSystemRepresentation,1);
        setenv("TOTK_ROMFS",romfs.fileSystemRepresentation,1);
        setenv("TOTK_AOC_ROOT",addons.fileSystemRepresentation,1);
        setenv("TOTK_ROMFS_PATCHES","0",1);
        setenv("TOTK_GPU_ALLOW_SUBMIT","1",1);
        setenv("TOTK_GPU_MIDCLEAR","1",1);
        setenv("TOTK_OPERATION_MODE","handheld",0);
        setenv("TOTK_INPUT_FILE",commands.fileSystemRepresentation,1);
        setenv("TOTK_SLOT_OWNER","user",0);
        setenv("TOTK_SLOT_PURPOSE","player",0);
        if(chdir(root.fileSystemRepresentation)){perror("chdir");return 1;}
        time_t now=time(NULL);char name[80];
        strftime(name,sizeof name,"castlevania-%Y%m%d-%H%M%S",localtime(&now));
        NSString *log=[logs stringByAppendingPathComponent:[NSString stringWithFormat:@"%s-%d.log",name,getpid()]];
        FILE *lf=fopen(log.fileSystemRepresentation,"w");
        if(lf){dup2(fileno(lf),STDOUT_FILENO);dup2(fileno(lf),STDERR_FILENO);fclose(lf);}
        char *const args[]={(char *)host.fileSystemRepresentation,(char *)images.fileSystemRepresentation,"boot",NULL};
        execv(args[0],args);
        fprintf(stderr,"[castlevania] execv failed: %s\n",strerror(errno));
        return 1;
    }
}
