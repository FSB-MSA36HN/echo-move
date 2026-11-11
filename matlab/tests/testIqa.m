function tests = testIqa
tests = functiontests(localfunctions);
end

function testBlurLowersSharpness(tc)
rng(0); sharp = rand(120, 160);
blurred = conv2(sharp, ones(9)/81, 'same');
verifyGreaterThan(tc, iqa.blurScore(sharp), iqa.blurScore(blurred));
end

function testUniformImageHasNoContrast(tc)
verifyEqual(tc, iqa.contrastScore(0.5*ones(64)), 0, 'AbsTol', 1e-9);
end

function testDarkImageLowExposure(tc)
verifyLessThan(tc, iqa.exposureScore(0.01*ones(64)), 10);
end

function testScoresInRange(tc)
rng(1); g = rand(96, 128);
vals = [iqa.mscnQuality(g) iqa.piqeFull(g) iqa.blurScore(g) ...
        iqa.contrastScore(g) iqa.noiseScore(g) iqa.exposureScore(g)];
verifyTrue(tc, all(vals >= 0 & vals <= 100));
end

function testOverallWeights(tc)
verifyEqual(tc, iqa.overall(100,100,100,100,100,[0.25 0.25 0.2 0.15 0.15]), 100, 'AbsTol', 1e-9);
end
