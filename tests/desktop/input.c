// SPDX-License-Identifier: MIT
#include <wayland-client.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "fake-input-client.h"
static struct org_kde_kwin_fake_input *input;
static void global(void *data,struct wl_registry *r,uint32_t name,const char *interface,uint32_t version) {
    if(!strcmp(interface,"org_kde_kwin_fake_input")) input=wl_registry_bind(r,name,&org_kde_kwin_fake_input_interface,version<5?version:5);
}
static void removed(void *d,struct wl_registry *r,uint32_t n){}
int main(int argc,char **argv) {
    struct wl_display *display=wl_display_connect(NULL);
    if(!display)return 3;
    struct wl_registry *registry=wl_display_get_registry(display);
    const struct wl_registry_listener listener={global,removed};
    wl_registry_add_listener(registry,&listener,NULL);
    wl_display_roundtrip(display);
    if(!input)return 4;
    org_kde_kwin_fake_input_authenticate(input,"Lumen Menütest","Ausschließlich eigene virtuelle Testsitzung");
    wl_display_roundtrip(display);
    char line[256],operation[32]; double x,y; int code;
    while(fgets(line,sizeof(line),stdin)) {
        if(sscanf(line,"%31s %lf %lf",operation,&x,&y)==3 && (!strcmp(operation,"click") || !strcmp(operation,"right") || !strcmp(operation,"move"))) {
            org_kde_kwin_fake_input_pointer_motion_absolute(input,wl_fixed_from_double(x),wl_fixed_from_double(y));wl_display_roundtrip(display);
            if(strcmp(operation,"move")) {
            org_kde_kwin_fake_input_button(input,!strcmp(operation,"right")?273:272,1);wl_display_roundtrip(display);
            org_kde_kwin_fake_input_button(input,!strcmp(operation,"right")?273:272,0);wl_display_roundtrip(display);
            }
        } else if(!strcmp(line,"down\n") || !strcmp(line,"up\n")){
            fprintf(stderr,"Button received: %s",line);fflush(stderr);
            org_kde_kwin_fake_input_button(input,272,!strcmp(line,"down\n"));wl_display_roundtrip(display);
            fprintf(stderr,"Button completed: %s",line);fflush(stderr);
        } else if(sscanf(line,"press %d",&code)==1){
            org_kde_kwin_fake_input_keyboard_key(input,code,1);wl_display_roundtrip(display);
        } else if(sscanf(line,"release %d",&code)==1){
            org_kde_kwin_fake_input_keyboard_key(input,code,0);wl_display_roundtrip(display);
        } else if(sscanf(line,"key %d",&code)==1) {
            org_kde_kwin_fake_input_keyboard_key(input,code,1);wl_display_roundtrip(display);
            org_kde_kwin_fake_input_keyboard_key(input,code,0);wl_display_roundtrip(display);
        } else return 5;
        puts("OK");fflush(stdout);
    }
    org_kde_kwin_fake_input_destroy(input);
    wl_display_roundtrip(display);wl_display_disconnect(display);return 0;
}
