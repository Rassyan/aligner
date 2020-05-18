package_windows64:
	curl https://ffmpeg.zeranoe.com/builds/win64/shared/ffmpeg-4.2-win64-shared.zip -o target/ffmpeg.zip
	unzip target/ffmpeg.zip -d target
	mv target/ffmpeg-4.2-win64-shared target/ffmpeg
	echo
	mkdir target/alass-windows64
	mkdir target/alass-windows64/ffmpeg
	mkdir target/alass-windows64/bin
	curl https://www.gnu.org/licenses/gpl-3.0.txt > target/alass-windows64/bin/LICENSE.txt
	cp target/ffmpeg/LICENSE.txt target/alass-windows64/ffmpeg/LICENSE.txt
	cp target/ffmpeg/README.txt target/alass-windows64/ffmpeg/README.txt
	cp -r target/ffmpeg/bin target/alass-windows64/ffmpeg/bin
	rm target/alass-windows64/ffmpeg/bin/ffplay.exe
	cargo build --release --target x86_64-pc-windows-gnu
	cp target/x86_64-pc-windows-gnu/release/alass-cli.exe target/alass-windows64/bin
	echo -ne '@echo off\r\nset ALASS_FFMPEG_PATH=%~dp0ffmpeg\\bin\\ffmpeg.exe\r\nset ALASS_FFPROBE_PATH=%~dp0ffmpeg\\bin\\ffprobe.exe\r\n"%~dp0bin\\alass-cli.exe" %*\r\n' > target/alass-windows64/alass.bat
	( cd target; zip -J -r alass-windows64.zip alass-windows64 )


clean_windows64:
	rm target/alass-windows64.zip -f
	rm target/ffmpeg-4.2-win64-shared.zip -f
	rm target/ffmpeg-4.2-win64-shared -rf
	rm target/ffmpeg -rf
	rm target/alass-windows64 -rf

package_linux64:
	cargo build --release --target x86_64-unknown-linux-musl
	cp ./target/x86_64-unknown-linux-musl/release/alass-cli ./target/alass-linux64
