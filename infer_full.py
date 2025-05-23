from segment_model.model import build_llm_seg
import torch
from torch.cuda.amp import autocast
from PIL import Image
from data_utils.utils import load_image
from torchvision import transforms
from llava.mm_utils import process_images
from llava.mm_utils import tokenizer_image_token
import cv2
import numpy as np
import os

def load_model():
    model, tokenizer, image_processor, config = build_llm_seg(
        model_path="/home/mamba/ML_project/Testing/Huy/llm_seg/weight/llava-med-v1.5-mistral-7b",
        model_base=None,
        load_8bit=False,
        load_4bit=False,
        device="cuda:2"
    )
    # model = model.to("cpu")
    tokenizer = model.load_model("/home/mamba/ML_project/Testing/Huy/llm_seg/training_results/weights3_full/llm_seg_12")
    model = model.to("cuda:2")
    return model, tokenizer, image_processor, config

def transform_for_sam(image_path):
    image_sam_transform = transforms.Compose([
        transforms.Resize((1024, 1024)),
        # transforms.ToTensor(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                            [0.229, 0.224, 0.225])
    ])

    image = load_image(image_path)
    image_tensor = image_sam_transform(image)
    return image_tensor.to(torch.float32).unsqueeze(0)

def load_image_for_vlm(image_path, image_processor, config):
    image_pil = load_image(image_path)
    image_tensor = process_images(
        [image_pil],
        image_processor,
        config
    )
    return image_tensor.to(torch.float16)

def process_prompt(prompt, tokenizer):
    # prompt_for_vlm = "<image>" + " You are doing the segmentation." + prompt
    prompt_for_vlm = "<image>\n" + f"### User: {prompt} \n"
    input_ids = tokenizer_image_token(
        prompt_for_vlm,
        tokenizer,
        -200,
        return_tensors="pt"
    )
    return input_ids.to(torch.int64).unsqueeze(0)

def process_prompt_seg(prompt, tokenizer):
    prompt_for_vlm = "<image> \n" + prompt
    input_ids = tokenizer_image_token(
        prompt_for_vlm,
        tokenizer,
        -200,
        return_tensors="pt"
    )
    return input_ids.to(torch.int64).unsqueeze(0)

def infer(
    prompt,
    image_path,
    image_processor,
    model,
    tokenizer,
    config,
    device = "cuda:2"
):
    image_tensor = load_image_for_vlm(image_path, image_processor, config)
    image_tensor_for_sam = transform_for_sam(image_path)
    image_tensor_for_sam = image_tensor_for_sam.to(device)
    image_tensor = image_tensor.to(device)
    input_ids = process_prompt(prompt, tokenizer)
    input_ids_for_seg = process_prompt_seg(prompt, tokenizer).to(device)
    input_ids = input_ids.to(device)
    # print(input_ids.shape)
    # print(image_tensor.shape)
    # print(image_tensor.dtype)
    print(input_ids)
    model.eval()
    model.to(device)
    # threshold = 0.5
    with autocast(dtype=torch.float16):
        with torch.no_grad():
            output_mask, output_ids = model.generate(
                input_ids = input_ids,
                input_ids_for_seg = input_ids_for_seg,
                image_tensor_for_vlm = image_tensor,
                image_tensor_for_image_enc = image_tensor_for_sam,
                attention_mask = None,
                temperature=0.2,
                max_new_tokens=512,
                top_p=0.95
            )
            print(output_mask.shape, output_ids.shape)
            print(output_ids)
            print(output_ids[0, input_ids.shape[1]:])
            print(output_ids[0, :])
            # outputs = tokenizer.decode(output_ids[0, input_ids.shape[1]:], skip_special_tokens=True)
            outputs_1 = tokenizer.decode(output_ids[0, :], skip_special_tokens=True)
            # print("Output:", outputs)
            # print("Output 1:", outputs_1)
            res = output_mask.sigmoid().cpu().numpy().squeeze()
            # res = (res > 0).astype(np.uint8)
            print(res.shape)
            # res = masks.transpose(1, 2, 0)
            # res = masks
            print(res.min(), res.max())
            print(res.shape)
            res = (res - res.min()) / (res.max() - res.min() + 1e-8)
            # res = (res > 0.3).astype(np.uint8)
            # cv2.imwrite("output_mask.png", res* 255)
            return res, outputs_1
            

            # outputs_answers = tokenizer.batch_decode(
            #     output_ids[:, input_ids.shape[1]:],
            #     skip_special_tokens=True
            # )[0]
            # print(outputs_answers)

if __name__ == "__main__":
    import pandas as pd
    model, tokenizer, image_processor, config = load_model()
    # image_path = "/home/mamba/ML_project/Testing/Huy/llm_seg/dataset/data/brain_tumors_ct_scan/train_images/2.png"
    # prompt = " CT scan demonstrating a dural-based mass along the convexity suggestive of meningioma."
    results_path = "results/lm_seg_test_3_full_2_ckpt_12"
    
    mask_path = results_path + "/masks/"
    if not os.path.exists(results_path):
        os.makedirs(results_path)
        os.makedirs(mask_path)
    # df_res = pd.DataFrame(columns=["image_path", "mask_path", "prompt", "results"])

    list_csv_path = ["/home/mamba/ML_project/Testing/Huy/llm_seg/dataset/annotation_v2/" + df_dir for df_dir in os.listdir("/home/mamba/ML_project/Testing/Huy/llm_seg/dataset/annotation_v2")]
    # df = pd.read_csv("/home/mamba/ML_project/Testing/Huy/llm_seg/dataset/annotation1/annotation_v1/lung_Xray.csv")
    # len(df)
    # cnt =0 
    for csv_path in list_csv_path:
        df = pd.read_csv(csv_path)
        image_list = []
        mask_list = []
        prompt_list = []
        answer_list = []
        for i in range(len(df)):
            # if cnt > 10:
                # break
            if df.iloc[i]["split"] == "test":
                # cnt+=1
                # beo
                image_path = "/home/mamba/ML_project/Testing/Huy/llm_seg/dataset/data/" + df.iloc[i]["image_path"]
                idx = df.iloc[i]["image_path"].split("/")[-1].split(".")[0]
                modal = df.iloc[i]["image_path"].split("/")[0]
                prompt = df.iloc[i]["question"]
                print("Image path:", image_path)
                print("Prompt:", prompt)
                mask, answer = infer(
                    prompt,
                    image_path,
                    image_processor,
                    model,
                    tokenizer,
                    config
                )
                mask = mask * 255
                # mask = mask.astype(np.uint8)
                if not os.path.exists(mask_path + "/" + modal):
                    os.makedirs(mask_path + "/" + modal)
                save_mask_path = mask_path + f"/{modal}/" + str(idx) + ".png"
                cv2.imwrite(save_mask_path, mask)
                print("Save mask path:", save_mask_path, "| Answer:", answer)
                image_list.append(df.iloc[i]["image_path"])
                mask_list.append(save_mask_path)
                prompt_list.append(prompt)
                answer_list.append(answer.replace("\n","").replace("### Assistant: ","").replace("### User: ","").replace("You are doing the segmentation for the tumour with the condition: ",""))
                # df_res = pd.concat([df_res, pd.DataFrame({"image_path": [df.iloc[i]["image_path"]], "mask_path": [save_mask_path], "prompt": [prompt], "results": [answer]})], ignore_index=True)
        df_res = pd.DataFrame({
            "image_path": image_list,
            "mask_path": mask_list,
            "prompt": prompt_list,
            "results": answer_list
        })
        print("Number of answer:", len(answer_list), "Number of image:", len(image_list), "Number of mask:", len(mask_list))
        df_res.to_csv(results_path + f"/results_{modal}.csv", index=False)

    # infer(
    #     prompt,
    #     image_path,
    #     image_processor,
    #     model,
    #     tokenizer,
    #     config
    # )


# model.to("cuda:1")
