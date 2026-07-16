# proguard-rules.pro — YiLuAn Android
# ANDROID-DEV-B0-CORE: 骨架占位，release 未开启 minify。
# kotlinx.serialization 保留规则（后续开启 R8 时生效）。
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class **$$serializer { *; }
-keepclasseswithmembers class * {
    kotlinx.serialization.KSerializer serializer(...);
}
