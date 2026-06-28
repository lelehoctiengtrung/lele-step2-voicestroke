const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { execSync } = require('child_process');

// 配置参数
const CONFIG = {
    character: '中', // 要生成的汉字
    width: 500,
    height: 500,
    fps: 15, // 帧率
    outputDir: './output',
    tempDir: './temp',
    mode: process.env.HANZI_RENDER_MODE || 'transparent'
};

// 确保输出目录存在
if (!fs.existsSync(CONFIG.outputDir)) {
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
}
if (!fs.existsSync(CONFIG.tempDir)) {
    fs.mkdirSync(CONFIG.tempDir, { recursive: true });
}

// 检查FFmpeg是否可用
function checkFFmpeg() {
    try {
        execSync('ffmpeg -version', { stdio: 'ignore' });
        return true;
    } catch {
        return false;
    }
}

function getContentType(filePath) {
    const extension = path.extname(filePath).toLowerCase();
    if (extension === '.html') return 'text/html; charset=utf-8';
    if (extension === '.js') return 'application/javascript; charset=utf-8';
    if (extension === '.json') return 'application/json; charset=utf-8';
    if (extension === '.css') return 'text/css; charset=utf-8';
    if (extension === '.svg') return 'image/svg+xml';
    if (extension === '.png') return 'image/png';
    if (extension === '.gif') return 'image/gif';
    return 'application/octet-stream';
}

function getBrowserExecutablePath() {
    const candidates = [
        process.env.PUPPETEER_EXECUTABLE_PATH,
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium'
    ].filter(Boolean);

    for (const candidate of candidates) {
        if (fs.existsSync(candidate)) {
            return candidate;
        }
    }

    return null;
}

function startStaticServer(rootDir) {
    const server = http.createServer((req, res) => {
        try {
            const requestUrl = new URL(req.url, 'http://127.0.0.1');
            const pathname = decodeURIComponent(requestUrl.pathname === '/' ? '/index.html' : requestUrl.pathname);
            const requestedPath = path.resolve(rootDir, `.${pathname}`);

            if (!requestedPath.startsWith(rootDir + path.sep) && requestedPath !== rootDir) {
                res.writeHead(403);
                res.end('Forbidden');
                return;
            }

            fs.readFile(requestedPath, (error, content) => {
                if (error) {
                    const statusCode = error.code === 'ENOENT' ? 404 : 500;
                    res.writeHead(statusCode, { 'Content-Type': 'text/plain; charset=utf-8' });
                    res.end(statusCode === 404 ? 'Not Found' : error.message);
                    return;
                }

                res.writeHead(200, { 'Content-Type': getContentType(requestedPath) });
                res.end(content);
            });
        } catch (error) {
            res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
            res.end(error.message);
        }
    });

    return new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const { port } = server.address();
            resolve({
                server,
                origin: `http://127.0.0.1:${port}`
            });
        });
    });
}

function stopStaticServer(server) {
    return new Promise((resolve, reject) => {
        if (!server || !server.listening) {
            resolve();
            return;
        }

        server.close(error => {
            if (error) {
                reject(error);
                return;
            }
            resolve();
        });
    });
}

async function generateGIF(character) {
    console.log(`开始生成汉字 "${character}" 的笔顺动画GIF...`);

    const { server, origin } = await startStaticServer(__dirname);
    let browser;

    const tempFrameDir = path.join(CONFIG.tempDir, character);
    if (!fs.existsSync(tempFrameDir)) {
        fs.mkdirSync(tempFrameDir, { recursive: true });
    }

    try {
        const executablePath = getBrowserExecutablePath();
        if (executablePath) {
            console.log(`使用浏览器: ${executablePath}`);
        }

        browser = await puppeteer.launch({
            headless: 'new',
            executablePath: executablePath || undefined,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        browser.on('disconnected', () => {
            console.error('浏览器连接已断开');
        });

        const page = await browser.newPage();
        page.on('pageerror', error => {
            console.error('页面脚本错误:', error.message);
        });
        page.on('error', error => {
            console.error('页面错误:', error.message);
        });
        page.on('requestfailed', request => {
            const failure = request.failure();
            console.error(`资源加载失败: ${request.url()} - ${failure ? failure.errorText : 'unknown error'}`);
        });

        await page.setViewport({
            width: CONFIG.width,
            height: CONFIG.height,
            deviceScaleFactor: 2
        });

        // 加载HTML页面
        await page.goto(`${origin}/index.html?char=${encodeURIComponent(character)}&mode=${encodeURIComponent(CONFIG.mode)}&mock=1`, {
            waitUntil: 'networkidle0',
            timeout: 30000
        });

        // 等待Hanzi Writer加载
        await page.waitForFunction(() => window.writer !== undefined, { timeout: 10000 });

        const loadError = await page.evaluate(() => window.loadError || null);
        if (loadError) {
            throw new Error(loadError);
        }

        const writerExists = await page.evaluate(() => typeof window.HanziWriter !== 'undefined');
        if (!writerExists) {
            throw new Error('HanziWriter 未加载成功');
        }

        const svgExists = await page.evaluate(() => !!document.querySelector('svg'));
        if (!svgExists) {
            throw new Error(`未能渲染汉字 "${character}"`);
        }

        await new Promise(r => setTimeout(r, 500));
        const browserPages = await browser.pages();
        if (browserPages.length === 0) {
            throw new Error('浏览器在渲染开始前已退出');
        }

        // 等待动画准备就绪（增加超时时间，并添加更宽松的检查）
        try {
            await page.waitForFunction(() => window.animationReady === true, { timeout: 15000 });
        } catch {
            console.warn('等待animationReady超时，继续执行...');
            // 即使超时也继续，给一些额外时间
            await new Promise(r => setTimeout(r, 1000));
        }

        
        console.log('开始录制动画帧...');
        
        // 额外等待确保渲染完成
        await new Promise(r => setTimeout(r, 500));
        
        // 录制帧
        const frameInterval = 1000 / CONFIG.fps; // 每帧间隔（毫秒）
        const totalDuration = await page.evaluate(() => window.totalAnimationDuration || 10000);
        console.log(`使用动态录制时长: ${totalDuration} 毫秒`);
        const totalFrames = Math.ceil(totalDuration / frameInterval);
        
        // 启动动画并标记开始，使用进度回调
        await page.evaluate(() => {
            if (window.writer) {
                window.animationStarted = true;
                window.writer.animateCharacter({
                    onProgress: (progress) => {
                        window.animationProgress = progress;
                    }
                });
            }
        });
        
        // 等待动画真正开始 - 等待第一个笔画出现
        // 通过检查SVG路径元素或等待一段时间
        let animationDetected = false;
        for (let check = 0; check < 60; check++) {
            await new Promise(r => setTimeout(r, 50));
            const hasStroke = await page.evaluate(() => {
                // 检查SVG路径元素
                const svg = document.querySelector('svg');
                if (svg) {
                    const paths = svg.querySelectorAll('path');
                    // 检查是否有路径的stroke-dasharray或stroke-dashoffset变化（表示动画进行中）
                    for (let path of paths) {
                        const style = window.getComputedStyle(path);
                        const strokeDasharray = style.strokeDasharray;
                        if (strokeDasharray && strokeDasharray !== 'none' && strokeDasharray !== '0px') {
                            return true;
                        }
                        // 或者检查路径是否可见
                        if (path.getAttribute('stroke') && path.getAttribute('stroke') !== 'none') {
                            return true;
                        }
                    }
                }
                return false;
            });
            
            if (hasStroke) {
                animationDetected = true;
                console.log('检测到动画开始');
                break;
            }
        }
        
        // 即使没检测到，也等待一段时间确保动画开始
        if (!animationDetected) {
            console.log('等待动画启动...');
            await new Promise(r => setTimeout(r, 500));
        }
        
        // 在动画进行的同时录制帧
        for (let i = 0; i < totalFrames; i++) {
            const framePath = path.join(tempFrameDir, `frame${String(i).padStart(4, '0')}.png`);
            
            await page.screenshot({
                path: framePath,
                omitBackground: CONFIG.mode === 'transparent',
                clip: {
                    x: 0,
                    y: 0,
                    width: CONFIG.width,
                    height: CONFIG.height
                }
            });
            
            // 等待下一帧 (使用RAF mock进行步进)
            await page.evaluate((ms) => {
                if (window.stepAnimation) {
                    window.stepAnimation(ms);
                }
            }, frameInterval);
            
            // 显示进度
            if ((i + 1) % 10 === 0 || i === totalFrames - 1) {
                console.log(`已录制 ${i + 1}/${totalFrames} 帧`);
            }
        }
        
        console.log('开始生成GIF...');

        const outputName = CONFIG.mode === 'transparent' ? `${character}-transparent.gif` : `${character}.gif`;
        const outputPath = path.join(CONFIG.outputDir, outputName);

        // 使用FFmpeg生成GIF
        if (checkFFmpeg()) {
            console.log('使用FFmpeg生成GIF...');
            const outputWidth = CONFIG.width;
            const outputHeight = CONFIG.height;
            const vf = CONFIG.mode === 'transparent'
                ? `scale=${outputWidth}:${outputHeight}:flags=lanczos,split[s0][s1];[s0]palettegen=reserve_transparent=1:transparency_color=000000[p];[s1][p]paletteuse=alpha_threshold=128`
                : `scale=${outputWidth}:${outputHeight}:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse`;
            const ffmpegCmd = `ffmpeg -y -framerate ${CONFIG.fps} -i "${path.join(tempFrameDir, 'frame%04d.png')}" -vf "${vf}" -loop -1 "${outputPath}"`;
            execSync(ffmpegCmd, { stdio: 'inherit' });
            console.log(`✓ GIF生成完成: ${outputPath}`);

            if (CONFIG.mode === 'transparent') {
                const webmPath = path.join(CONFIG.outputDir, `${character}-transparent.webm`);
                const webmCmd = `ffmpeg -y -framerate ${CONFIG.fps} -i "${path.join(tempFrameDir, 'frame%04d.png')}" -vf "scale=${outputWidth}:${outputHeight}:flags=lanczos,format=yuva420p" -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 "${webmPath}"`;
                execSync(webmCmd, { stdio: 'inherit' });
                console.log(`✓ WebM透明视频生成完成: ${webmPath}`);
            }
        } else {
            console.warn('\n⚠️  FFmpeg未安装，无法自动生成GIF。');
            console.log('PNG帧已保存在:', tempFrameDir);
            console.log('\n请安装FFmpeg后运行以下命令生成GIF:');
            const outputWidth = CONFIG.width;
            const outputHeight = CONFIG.height;
            const vf = CONFIG.mode === 'transparent'
                ? `scale=${outputWidth}:${outputHeight}:flags=lanczos,split[s0][s1];[s0]palettegen=reserve_transparent=1:transparency_color=000000[p];[s1][p]paletteuse=alpha_threshold=128`
                : `scale=${outputWidth}:${outputHeight}:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse`;
            console.log(`ffmpeg -y -framerate ${CONFIG.fps} -i "${path.join(tempFrameDir, 'frame%04d.png')}" -vf "${vf}" "${outputPath}"`);
            console.log('\n或安装FFmpeg:');
            console.log('  macOS: brew install ffmpeg');
            console.log('  Linux: sudo apt-get install ffmpeg');
            throw new Error('需要FFmpeg来生成GIF');
        }
        
        // 清理临时文件
        const files = fs.readdirSync(tempFrameDir);
        for (const file of files) {
            fs.unlinkSync(path.join(tempFrameDir, file));
        }
        fs.rmdirSync(tempFrameDir);
        
        return outputPath;
        
    } catch (error) {
        console.error('生成GIF时出错:', error);
        throw error;
    } finally {
        if (browser) {
            await browser.close();
        }
        await stopStaticServer(server);
    }
}

// 从JSON文件读取汉字列表
function getCharactersFromJSON(jsonPath) {
    try {
        const jsonData = fs.readFileSync(jsonPath, 'utf-8');
        const data = JSON.parse(jsonData);

        // 支持简化格式: ["中","文"]
        if (Array.isArray(data)) {
            const characters = data
                .filter(item => typeof item === 'string' && item.trim())
                .map(item => item.trim());
            return [...new Set(characters)];
        }

        // 兼容旧格式: { data: { records: [ { word: "中" } ] } }
        const words = [];
        if (data.data && data.data.records) {
            data.data.records.forEach(record => {
                if (record.word) {
                    words.push(record.word);
                }
            });
        }

        return [...new Set(words)];
    } catch (error) {
        console.error('读取JSON文件失败:', error);
        throw error;
    }
}

// 并发控制函数
async function runWithConcurrencyLimit(tasks, concurrency = 3) {
    const results = [];
    const errors = [];
    const skipped = [];
    let index = 0;
    
    const runTask = async (character, taskIndex) => {
        // 检查文件是否已存在
        const outputName = CONFIG.mode === 'transparent' ? `${character}-transparent.gif` : `${character}.gif`;
        const outputPath = path.join(CONFIG.outputDir, outputName);
        if (fs.existsSync(outputPath)) {
            skipped.push({ character, path: outputPath });
            console.log(`⊘ [${taskIndex + 1}/${tasks.length}] 跳过 "${character}" (文件已存在): ${outputPath}`);
            return;
        }
        
        try {
            console.log(`\n[${taskIndex + 1}/${tasks.length}] 开始生成汉字 "${character}" 的GIF...`);
            const generatedPath = await generateGIF(character);
            results.push({ character, path: generatedPath, success: true });
            console.log(`✓ [${taskIndex + 1}/${tasks.length}] 成功！GIF文件已保存到: ${generatedPath}`);
        } catch (error) {
            console.error(`✗ [${taskIndex + 1}/${tasks.length}] 生成失败: ${error.message}`);
            errors.push({ character, error: error.message });
        }
    };
    
    // 创建并发池
    const workers = [];
    for (let i = 0; i < concurrency; i++) {
        workers.push((async () => {
            while (index < tasks.length) {
                const currentIndex = index++;
                if (currentIndex < tasks.length) {
                    await runTask(tasks[currentIndex], currentIndex);
                }
            }
        })());
    }
    
    // 等待所有工作线程完成
    await Promise.all(workers);
    
    return { results, errors, skipped };
}

// 主函数
async function main() {
    // 检查是否提供了JSON文件路径
    const jsonPath = process.argv[2];
    let characters = [];
    let concurrency = 3; // 默认并发数
    
    // 检查是否有并发数参数
    if (process.argv[3] && !isNaN(parseInt(process.argv[3]))) {
        concurrency = parseInt(process.argv[3]);
    }
    
    if (jsonPath && jsonPath.endsWith('.json')) {
        // 从JSON文件读取汉字列表
        console.log(`从文件读取汉字列表: ${jsonPath}`);
        characters = getCharactersFromJSON(jsonPath);
        console.log(`找到 ${characters.length} 个汉字: ${characters.join(', ')}`);
        console.log(`并发数: ${concurrency}`);
    } else {
        // 单个汉字模式
        const character = process.argv[2] || CONFIG.character;
        characters = [character];
    }
    
    if (characters.length === 0) {
        console.error('没有找到要生成的汉字');
        process.exit(1);
    }
    
    // 并行生成每个汉字的GIF
    const startTime = Date.now();
    const { results, errors, skipped } = await runWithConcurrencyLimit(characters, concurrency);
    const endTime = Date.now();
    const duration = ((endTime - startTime) / 1000 / 60).toFixed(2);
    
    // 输出总结
    console.log(`\n========== 生成完成 ==========`);
    console.log(`总耗时: ${duration} 分钟`);
    console.log(`成功: ${results.length} 个`);
    console.log(`跳过: ${skipped.length} 个 (文件已存在)`);
    console.log(`失败: ${errors.length} 个`);
    
    if (errors.length > 0) {
        console.log(`\n失败的汉字:`);
        errors.forEach(({ character, error }) => {
            console.log(`  - ${character}: ${error}`);
        });
    }
}

// 运行
if (require.main === module) {
    main();
}

module.exports = { generateGIF };

