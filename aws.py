import boto3

def detect_labels_local_file(photo):
    client=boto3.client('rekognition')
    with open(photo, 'rb') as image:
        response = client.detect_labels(Image={'Bytes': image.read()})

    result = []
    for label in response['Labels']:

        Name = label["Name"]
        Confidence = label["Confidence"]

        result.append((f"{Name}일 확률은 {Confidence : .2f}%입니다"))
        
    return "<br/>".join(map(str, result))  

# AWS Amazon Rekognition 서비스 활용하여 이미지 분석해보자
# 샘플 코드

def compare_faces_aws(sourceFile, targetFile):
    result = []
    client = boto3.client('rekognition')
    imageSource = open(sourceFile, 'rb')
    imageTarget = open(targetFile, 'rb')
    response = client.compare_faces(SimilarityThreshold=0,
                                    SourceImage={'Bytes': imageSource.read()},
                                    TargetImage={'Bytes': imageTarget.read()})
    for faceMatch in response['FaceMatches']:
        position = faceMatch['Face']['BoundingBox']
        similarity = faceMatch['Similarity']
        result.append((f"동일 인물일 확률 : {similarity:.2f}%"))
    imageSource.close()
    imageTarget.close()
    return "<br/>".join(map(str,result))
