import vpk

#your vpk will have the folder structure within the input folder

newpak = vpk.new("./input")
newpak.save("mod.vpk")
pak = newpak.save_and_open("mod.vpk")